# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrKpiDailyWizard(models.TransientModel):
    _name = "hr.kpi.daily.wizard"
    _description = "Nhập KPI theo ngày"

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
    employee_id = fields.Many2one("hr.employee", string="Nhân viên", required=True)

    @api.model
    def _department_domain(self):
        Sheet = self.env["hr.kpi.monthly.sheet"]
        return Sheet._department_domain()

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

    @api.onchange("department_id")
    def _onchange_department_id(self):
        if self.department_id and not self.employee_id:
            members = self.department_id.member_ids
            if len(members) == 1:
                self.employee_id = members[0]

    def _get_or_create_sheet(self):
        self.ensure_one()
        month_start = self.month_date.replace(day=1)
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

    def _get_or_create_employee_line(self, sheet):
        self.ensure_one()
        line = sheet.employee_ids.filtered(lambda l: l.employee_id == self.employee_id)
        if not line:
            line = self.env["hr.kpi.monthly.employee"].create({
                "sheet_id": sheet.id,
                "employee_id": self.employee_id.id,
            })
        else:
            line = line[0]
        if self.employee_id not in self.department_id.member_ids:
            raise UserError(self.env._("Nhân viên không thuộc bãi xe đã chọn."))
        return line

    @api.model
    def _sync_daily_lines(self, monthly_employee):
        """Ensure one line per day × daily criterion for the month."""
        sheet = monthly_employee.sheet_id
        sheet._check_captain_editable()
        start = sheet.month_date
        end = start + relativedelta(months=1, days=-1)
        criteria = self.env["hr.kpi.criterion"].search(self.env["hr.kpi.criterion"]._daily_criteria_domain())
        Daily = self.env["hr.kpi.daily.line"]
        existing = {
            (line.date, line.criterion_id.id): line
            for line in Daily.search([("monthly_employee_id", "=", monthly_employee.id)])
        }
        day = start
        to_create = []
        while day <= end:
            for criterion in criteria:
                key = (day, criterion.id)
                if key not in existing:
                    to_create.append({
                        "monthly_employee_id": monthly_employee.id,
                        "date": day,
                        "criterion_id": criterion.id,
                    })
            day += relativedelta(days=1)
        if to_create:
            Daily.create(to_create)

    def action_open_daily_grid(self):
        self.ensure_one()
        if not self.employee_id:
            raise UserError(self.env._("Chọn nhân viên để nhập KPI."))
        sheet = self._get_or_create_sheet()
        sheet._check_captain_editable()
        employee_line = self._get_or_create_employee_line(sheet)
        self._sync_daily_lines(employee_line)
        return employee_line.action_open_daily_lines()