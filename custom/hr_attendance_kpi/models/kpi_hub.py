# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


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

    def _refresh_day_lines(self):
        Daily = self.env["hr.kpi.daily.line"]
        for hub in self:
            hub.day_line_ids.unlink()
            if not hub.sheet_id:
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

            lines = []
            day = start
            while day <= end:
                lines.append({
                    "hub_id": hub.id,
                    "date": day,
                    "fail_count": fail_by_date.get(day, 0),
                })
                day += relativedelta(days=1)
            self.env["hr.kpi.hub.day"].create(lines)

    @api.onchange("department_id", "month_date")
    def _onchange_filters(self):
        self._update_sheet()
        self._refresh_day_lines()

    @api.model_create_multi
    def create(self, vals_list):
        hubs = super().create(vals_list)
        hubs._update_sheet()
        hubs._refresh_day_lines()
        return hubs

    def write(self, vals):
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
    _description = "Ngày KPI trên hub"
    _order = "date"

    hub_id = fields.Many2one("hr.kpi.hub", required=True, ondelete="cascade")
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
        hub = self.hub_id
        sheet = hub._get_or_create_sheet()
        sheet._check_captain_editable()
        sheet._ensure_employee_lines()
        self.env["hr.kpi.daily.wizard"]._sync_sheet_day(sheet, self.date)
        view = self.env.ref("hr_attendance_kpi.view_hr_kpi_daily_line_day_tree")
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("KPI ngày %s", self.date.strftime("%d/%m/%Y")),
            "res_model": "hr.kpi.daily.line",
            "view_mode": "list",
            "views": [(view.id, "list")],
            "domain": [
                ("sheet_id", "=", sheet.id),
                ("date", "=", self.date),
            ],
            "context": {
                "default_date": fields.Date.to_string(self.date),
                "kpi_hub_date": fields.Date.to_string(self.date),
            },
        }