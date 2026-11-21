# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrKpiHub(models.TransientModel):
    _name = "hr.kpi.hub"
    _description = "Đánh giá KPI"

    department_id = fields.Many2one(
        "hr.department",
        string="Bãi xe",
        required=True,
        domain=lambda self: self._department_domain(),
    )
    month_date = fields.Date(
        string="Tháng",
        required=True,
        help="Ngày đầu tháng.",
    )
    sheet_id = fields.Many2one(
        "hr.kpi.monthly.sheet",
        string="Bảng tháng",
        readonly=True,
    )
    sheet_state = fields.Selection(related="sheet_id.state", readonly=True)
    lock_deadline = fields.Date(related="sheet_id.lock_deadline", readonly=True)
    day_line_ids = fields.One2many("hr.kpi.hub.day", "hub_id", string="Ngày trong tháng")
    sheet_employee_ids = fields.One2many(
        related="sheet_id.employee_ids",
        string="Nhân viên",
        readonly=False,
    )

    @api.model
    def _department_domain(self):
        return self.env["hr.kpi.monthly.sheet"]._department_domain()

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        values.setdefault("month_date", today.replace(day=1))
        if "department_id" in fields_list and not values.get("department_id"):
            department_ids = self.env.user._hr_site_captain_department_ids()
            departments = self.env["hr.department"].browse(department_ids).exists()
            if len(departments) == 1:
                values["department_id"] = departments.id
        return values

    def _month_start(self):
        self.ensure_one()
        return self.month_date.replace(day=1)

    def _get_or_create_sheet(self):
        self.ensure_one()
        month_start = self._month_start()
        Sheet = self.env["hr.kpi.monthly.sheet"]
        sheet = Sheet.search([
            ("department_id", "=", self.department_id.id),
            ("month_date", "=", month_start),
        ], limit=1)
        if not sheet:
            sheet = Sheet.create({
                "department_id": self.department_id.id,
                "month_date": month_start,
            })
        else:
            sheet._ensure_employee_lines()
        return sheet

    def _update_sheet(self):
        for hub in self:
            if hub.department_id and hub.month_date:
                hub.sheet_id = hub._get_or_create_sheet()
            else:
                hub.sheet_id = False

    def _validate_day_line_commands(self, commands):
        for command in commands:
            if command[0] == 0 and not command[2].get("date"):
                raise ValidationError(self.env._("Mỗi ngày KPI phải có ngày."))
            if command[0] == 1 and "date" in command[2] and not command[2]["date"]:
                raise ValidationError(self.env._("Mỗi ngày KPI phải có ngày."))

    def _refresh_day_lines(self):
        Daily = self.env["hr.kpi.daily.line"]
        for hub in self:
            commands = [(5, 0, 0)]
            if not hub.sheet_id:
                hub.day_line_ids = commands
                continue
            start = hub._month_start()
            end = start + relativedelta(months=1, days=-1)
            fail_by_date = {}
            for group in Daily.read_group(
                [
                    ("sheet_id", "=", hub.sheet_id.id),
                    ("is_fail", "=", True),
                    ("date", ">=", start),
                    ("date", "<=", end),
                ],
                ["date"],
                ["date"],
            ):
                fail_by_date[group["date"]] = group["date_count"]

            day = start
            while day <= end:
                line_vals = {
                    "date": day,
                    "fail_count": fail_by_date.get(day, 0),
                }
                if isinstance(hub.id, int):
                    line_vals["hub_id"] = hub.id
                commands.append((0, 0, line_vals))
                day += relativedelta(days=1)
            self._validate_day_line_commands(commands)
            hub.day_line_ids = commands
            if hub.day_line_ids.filtered(lambda line: not line.date):
                raise ValidationError(self.env._("Mỗi ngày KPI phải có ngày."))

    @api.onchange("department_id", "month_date")
    def _onchange_filters(self):
        self._update_sheet()
        self._refresh_day_lines()

    def _ensure_persisted(self):
        """Lưu wizard (TransientModel) trước khi bấm nút trên dòng ngày trong form chưa lưu."""
        self.ensure_one()
        if not self.department_id or not self.month_date:
            raise UserError(self.env._("Chọn bãi xe và tháng trước."))
        persist_vals = {
            "department_id": self.department_id.id,
            "month_date": self.month_date,
        }
        if self.ids and self.exists():
            self.write(persist_vals)
            hub = self
        else:
            hub = self.create(persist_vals)
        hub._update_sheet()
        hub._refresh_day_lines()
        return hub

    @api.model
    def action_open_kpi_hub(self):
        hub = self.create({})
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Đánh giá KPI"),
            "res_model": self._name,
            "res_id": hub.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model_create_multi
    def create(self, vals_list):
        hubs = super().create(vals_list)
        hubs._update_sheet()
        hubs._refresh_day_lines()
        return hubs

    def write(self, vals):
        if "day_line_ids" in vals:
            self._validate_day_line_commands(vals["day_line_ids"])
        res = super().write(vals)
        if {"department_id", "month_date"}.intersection(vals):
            self._update_sheet()
            self._refresh_day_lines()
        return res

    def action_reload(self):
        self.ensure_one()
        self._update_sheet()
        self._refresh_day_lines()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def _require_sheet(self):
        self.ensure_one()
        if not self.sheet_id:
            raise UserError(self.env._("Chọn bãi xe và tháng trước."))
        return self.sheet_id

    def action_sheet_submit(self):
        self._require_sheet().action_submit()
        return self.action_reload()

    def action_sheet_recompute(self):
        self._require_sheet().action_recompute_all()
        return self.action_reload()

    def action_sheet_export(self):
        return self._require_sheet().action_export_xlsx()

    def action_sheet_hr_lock(self):
        self._require_sheet().action_hr_lock()
        return self.action_reload()

    def action_sheet_unlock(self):
        self._require_sheet().action_unlock_draft()
        return self.action_reload()


class HrKpiHubDay(models.TransientModel):
    _name = "hr.kpi.hub.day"
    _description = "Ngày trong tháng"
    _order = "date"

    hub_id = fields.Many2one(
        "hr.kpi.hub",
        string=" ",
        required=True,
        ondelete="cascade",
    )
    date = fields.Date(required=True)
    fail_count = fields.Integer(string="Số lỗi", readonly=True)
    weekday = fields.Char(compute="_compute_weekday")

    @api.depends("date")
    def _compute_weekday(self):
        labels = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")
        for line in self:
            if line.date:
                line.weekday = labels[line.date.weekday()]
            else:
                line.weekday = False

    def action_open_day(self):
        self.ensure_one()
        target_date = self.date
        if not target_date:
            raise UserError(self.env._("Thiếu ngày KPI."))
        hub = self.hub_id._ensure_persisted()
        day_line = hub.day_line_ids.filtered(lambda line: line.date == target_date)
        if not day_line:
            raise UserError(self.env._("Không tìm thấy ngày KPI trong tháng đã chọn."))
        target_date = day_line[0].date
        sheet = hub._get_or_create_sheet()
        sheet._check_captain_editable()
        sheet._ensure_employee_lines()
        self.env["hr.kpi.daily.wizard"]._sync_sheet_day(sheet, target_date)
        view = self.env.ref("hr_attendance_kpi.view_hr_kpi_daily_line_day_tree")
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("KPI ngày %s", target_date.strftime("%d/%m/%Y")),
            "res_model": "hr.kpi.daily.line",
            "view_mode": "list",
            "views": [(view.id, "list")],
            "domain": [
                ("sheet_id", "=", sheet.id),
                ("date", "=", target_date),
            ],
            "context": {
                "default_date": fields.Date.to_string(target_date),
                "kpi_hub_date": fields.Date.to_string(target_date),
            },
        }