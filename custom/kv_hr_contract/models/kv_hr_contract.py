import logging
import re

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

CONTRACT_NAME_RE = re.compile(r"HD\.(\d+)\.(\d+)$")


class KVHRVersion(models.Model):
    """Odoo 19: hr.contract was merged into hr.version (one version per
    employee change). The KV contract number ("HD.<year>.<nnn>") stays on
    hr.version.name; contract_year / contract_number keep their columns,
    which OpenUpgrade carries over when it renames hr_contract -> hr_version.
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

    @api.model
    def get_latest_contract_name(self, year=None):
        year = year or fields.Date.context_today(self).year
        latest = self.sudo().with_context(active_test=False).search(
            [("contract_year", "=", year)], order="contract_number desc", limit=1
        )
        number = latest.contract_number + 1 if latest else 1
        return "HD.%s.%03d" % (year, number)

    def action_kv_assign_contract_number(self):
        """Replaces the Odoo 18 default_get: in Odoo 19 every employee change
        creates a version, so numbering is explicit instead of automatic."""
        for version in self:
            if not CONTRACT_NAME_RE.match(version.name or ""):
                version.name = self.get_latest_contract_name()
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

    def action_kv_assign_contract_number(self):
        self.ensure_one()
        return self.version_id.action_kv_assign_contract_number()

    def action_kv_print_contract(self):
        self.ensure_one()
        return self.version_id.generate_pdf_action()
