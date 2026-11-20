# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrKpiDailyLine(models.Model):
    _name = "hr.kpi.daily.line"
    _description = "KPI theo ngày"
    _order = "date, criterion_id"

    monthly_employee_id = fields.Many2one(
        "hr.kpi.monthly.employee",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(related="monthly_employee_id.employee_id", store=True, index=True)
    sheet_id = fields.Many2one(related="monthly_employee_id.sheet_id", store=True)
    department_id = fields.Many2one(related="monthly_employee_id.department_id", store=True)
    company_id = fields.Many2one(related="monthly_employee_id.company_id", store=True)
    date = fields.Date(required=True, index=True)
    criterion_id = fields.Many2one("hr.kpi.criterion", required=True, index=True, ondelete="restrict")
    group_code = fields.Selection(related="criterion_id.group_code", store=True)
    is_fail = fields.Boolean(string="Lỗi", default=False)
    note = fields.Char(string="Ghi chú")

    display_name = fields.Char(compute="_compute_display_name")

    _sql_constraints = [
        (
            "employee_day_criterion_uniq",
            "unique(monthly_employee_id, date, criterion_id)",
            "Đã có dòng KPI cho tiêu chí này trong ngày đó.",
        ),
    ]

    @api.depends("date", "criterion_id", "employee_id")
    def _compute_display_name(self):
        for line in self:
            parts = [line.employee_id.name, line.criterion_id.name]
            if line.date:
                parts.append(line.date.strftime("%d/%m/%Y"))
            line.display_name = " — ".join(part for part in parts if part)

    @api.constrains("date", "monthly_employee_id", "criterion_id")
    def _check_month_and_group(self):
        for line in self:
            if line.criterion_id.deduction_type == "manual":
                raise ValidationError(self.env._("Nhóm A/B không nhập trên lưới ngày."))
            if not line.monthly_employee_id.month_date:
                continue
            start = line.monthly_employee_id.month_date
            end = start + relativedelta(months=1, days=-1)
            if not (start <= line.date <= end):
                raise ValidationError(self.env._("Ngày KPI phải thuộc tháng của bảng."))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._after_change_recompute()
        return lines

    def write(self, vals):
        if {"is_fail", "note"}.intersection(vals):
            self.monthly_employee_id.sheet_id._check_captain_editable()
        res = super().write(vals)
        if {"is_fail", "note", "criterion_id"}.intersection(vals):
            self._after_change_recompute()
        return res

    def unlink(self):
        employees = self.mapped("monthly_employee_id")
        for line in self:
            line.monthly_employee_id.sheet_id._check_captain_editable()
        res = super().unlink()
        employees.action_recompute()
        return res

    def _after_change_recompute(self):
        self.mapped("monthly_employee_id").action_recompute()

    @api.onchange("is_fail")
    def _onchange_is_fail(self):
        if self.is_fail and self.criterion_id.group_code == "E":
            self.note = self.note or self.env._("Vi phạm nghiêm trọng")