import logging
import re

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

CONTRACT_NAME_RE = re.compile(r"HD\.(\d+)\.(\d+)$")
# Serialises numbering between concurrent transactions (released at commit/rollback).
_NUMBER_LOCK_KEY = 4815162342


def _is_contract_number(name):
    return bool(CONTRACT_NAME_RE.match(name or ""))


class KVHRVersion(models.Model):
    """Odoo 19: hr.contract was merged into hr.version (one version per
    employee change). The KV contract number "HD.<year>.<nnn>" stays on
    hr.version.name; contract_year / contract_number keep their columns,
    which OpenUpgrade carries over when it renames hr_contract -> hr_version.

    Numbering rule (same idea as Odoo 18, where every new hr.contract got the
    next number):
    - a version is a contract only when contract_date_start is set; versions
      without it never get a number;
    - a version of an existing contract (same employee, same
      contract_date_start) shares that contract's number;
    - a version with a new contract_date_start whose name was copied from
      another contract of the employee gets the next number;
    - a valid HD.YYYY.NNN typed by the user is kept.
    """

    _inherit = "hr.version"

    contract_year = fields.Integer(compute="_compute_contract_parts", store=True)
    contract_number = fields.Integer(compute="_compute_contract_parts", store=True)

    @api.depends("name")
    def _compute_contract_parts(self):
        for record in self:
            matches = CONTRACT_NAME_RE.match(record.name or "")
            if matches:
                record.contract_year = int(matches.group(1))
                record.contract_number = int(matches.group(2))
            else:
                record.contract_year = 0
                record.contract_number = 0

    # ------------------------------------------------------------------
    # Numbering helpers
    # ------------------------------------------------------------------
    @api.model
    def _kv_numbering_disabled(self):
        ctx = self.env.context
        return bool(
            ctx.get("kv_skip_contract_number")
            or ctx.get("install_mode")
            or ctx.get("module")  # data files of a module being installed/updated
        )

    @api.model
    def _kv_next_contract_numbers(self, count=1, year=None):
        """Return `count` consecutive new numbers for `year` (default: this year)."""
        year = year or fields.Date.context_today(self).year
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (_NUMBER_LOCK_KEY,))
        self.env["hr.version"].flush_model(["name", "contract_year", "contract_number"])
        self.env.cr.execute(
            "SELECT COALESCE(MAX(contract_number), 0) FROM hr_version WHERE contract_year = %s",
            (year,),
        )
        last = self.env.cr.fetchone()[0]
        return ["HD.%s.%03d" % (year, last + i) for i in range(1, count + 1)]

    @api.model
    def get_latest_contract_name(self, year=None):
        return self._kv_next_contract_numbers(1, year)[0]

    def _kv_contract_number_to_reuse(self):
        """Number already used by another version of the same contract."""
        self.ensure_one()
        if not (self.employee_id and self.contract_date_start):
            return False
        sibling = self.sudo().with_context(active_test=False).search([
            ("id", "!=", self.id),
            ("employee_id", "=", self.employee_id.id),
            ("contract_date_start", "=", self.contract_date_start),
            ("contract_number", ">", 0),
        ], order="date_version, id", limit=1)
        return sibling.name or False

    def _kv_name_copied_from_other_contract(self):
        """True when this version carries the number of a *different* contract
        (different contract_date_start) of the same employee, i.e. the name
        was copied by create_version()/copy() for a renewal."""
        self.ensure_one()
        if not (self.employee_id and _is_contract_number(self.name)):
            return False
        return bool(self.sudo().with_context(active_test=False).search_count([
            ("id", "!=", self.id),
            ("employee_id", "=", self.employee_id.id),
            ("name", "=", self.name),
            ("contract_date_start", "!=", self.contract_date_start),
        ], limit=1))

    def _kv_ensure_contract_number(self):
        if self._kv_numbering_disabled():
            return
        todo = self.env["hr.version"]
        updates = {}
        for version in self.filtered("contract_date_start"):
            if _is_contract_number(version.name):
                if not version._kv_name_copied_from_other_contract():
                    continue  # typed by the user or same contract: keep it
            else:
                reuse = version._kv_contract_number_to_reuse()
                if reuse:
                    updates[version] = reuse
                    continue
            todo |= version
        if todo:
            numbers = self._kv_next_contract_numbers(len(todo))
            for version, number in zip(todo, numbers):
                updates[version] = number
        for version, number in updates.items():
            version.with_context(kv_skip_contract_number=True).sudo().write({"name": number})
            _logger.info("kv_hr_contract: version %s (employee %s) -> %s",
                         version.id, version.employee_id.id, number)

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        versions._kv_ensure_contract_number()
        return versions

    def write(self, vals):
        res = super().write(vals)
        if (
            {"contract_date_start", "name", "employee_id"} & set(vals)
            and not self.env.context.get("kv_skip_contract_number")
        ):
            self._kv_ensure_contract_number()
        return res

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_kv_assign_contract_number(self):
        """Fallback button: same rule as the automatic numbering."""
        self.with_context(kv_skip_contract_number=False)._kv_ensure_contract_number()
        return True

    def generate_pdf_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/contracts/pdf/{self.id}",
            "target": "new",
        }


class KVHREmployee(models.Model):
    _inherit = "hr.employee"

    # hr.employee has its own `name`, so expose the version's contract number.
    kv_contract_name = fields.Char(
        string="Số hợp đồng",
        related="version_id.name",
        readonly=False,
        groups="hr.group_hr_manager",
    )
    kv_contract_number = fields.Integer(
        related="version_id.contract_number",
        groups="hr.group_hr_manager",
    )

    def action_kv_assign_contract_number(self):
        self.ensure_one()
        return self.version_id.action_kv_assign_contract_number()

    def action_kv_print_contract(self):
        self.ensure_one()
        return self.version_id.generate_pdf_action()
