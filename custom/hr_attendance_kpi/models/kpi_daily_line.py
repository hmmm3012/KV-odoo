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
    employee_id = fields.Many2one(
        "hr.employee",
        string="Nhân viên",
        compute="_compute_employee_id",
        inverse="_inverse_employee_id",
        store=True,
        index=True,
        domain=lambda self: self._employee_id_domain(),
    )
    sheet_id = fields.Many2one(related="monthly_employee_id.sheet_id", store=True)
    department_id = fields.Many2one(related="monthly_employee_id.department_id", store=True)
    company_id = fields.Many2one(related="monthly_employee_id.company_id", store=True)
    date = fields.Date(required=True, index=True)
    criterion_id = fields.Many2one(
        "hr.kpi.criterion",
        string="Tiêu chí",
        required=True,
        index=True,
        ondelete="restrict",
        domain=lambda self: self.env["hr.kpi.criterion"]._daily_criteria_domain(),
    )
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

    @api.depends("monthly_employee_id.employee_id")
    def _compute_employee_id(self):
        for line in self:
            line.employee_id = line.monthly_employee_id.employee_id

    def _inverse_employee_id(self):
        for line in self:
            if not line.employee_id:
                continue
            sheet = line.sheet_id or line._sheet_from_context()
            line.monthly_employee_id = line._monthly_employee_for(line.employee_id.id, sheet)

    @api.model
    def _employee_id_domain(self):
        sheet = self.env["hr.kpi.monthly.sheet"].browse(
            self.env.context.get("kpi_sheet_id")
        ).exists()
        if sheet and sheet.department_id:
            return [("department_id", "child_of", sheet.department_id.id)]
        return []

    def _sheet_from_context(self):
        sheet = self.env["hr.kpi.monthly.sheet"].browse(
            self.env.context.get("kpi_sheet_id")
        ).exists()
        if not sheet:
            raise UserError(self.env._("Thiếu thông tin bảng KPI tháng."))
        return sheet

    def _monthly_employee_for(self, employee_id, sheet=None):
        self.ensure_one()
        if not sheet:
            sheet = self.sheet_id or self._sheet_from_context()
        sheet._check_captain_editable()
        sheet._ensure_employee_lines()
        employee = self.env["hr.employee"].browse(employee_id)
        if employee not in sheet.department_id.member_ids:
            raise UserError(self.env._("Nhân viên không thuộc bãi xe đã chọn."))
        line = sheet.employee_ids.filtered(lambda l: l.employee_id == employee)
        if line:
            return line[0]
        return self.env["hr.kpi.monthly.employee"].create({
            "sheet_id": sheet.id,
            "employee_id": employee_id,
        })

    @api.model
    def _prepare_day_entry_vals(self, vals):
        vals = dict(vals)
        if not vals.get("date") and self.env.context.get("kpi_hub_date"):
            vals["date"] = fields.Date.to_date(self.env.context["kpi_hub_date"])
        vals.setdefault("is_fail", True)
        sheet_id = self.env.context.get("kpi_sheet_id")
        if vals.get("employee_id") and not vals.get("monthly_employee_id"):
            sheet = self.env["hr.kpi.monthly.sheet"].browse(sheet_id).exists()
            if not sheet and vals.get("sheet_id"):
                sheet = self.env["hr.kpi.monthly.sheet"].browse(vals["sheet_id"])
            if not sheet:
                raise UserError(self.env._("Thiếu thông tin bảng KPI tháng."))
            employee = self.env["hr.employee"].browse(vals["employee_id"])
            if employee not in sheet.department_id.member_ids:
                raise UserError(self.env._("Nhân viên không thuộc bãi xe đã chọn."))
            sheet._check_captain_editable()
            sheet._ensure_employee_lines()
            line = sheet.employee_ids.filtered(lambda l: l.employee_id == employee)
            vals["monthly_employee_id"] = (
                line[0].id
                if line
                else self.env["hr.kpi.monthly.employee"].create({
                    "sheet_id": sheet.id,
                    "employee_id": employee.id,
                }).id
            )
        if sheet_id:
            self.env["hr.kpi.monthly.sheet"].browse(sheet_id)._check_captain_editable()
        return vals

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "date" in fields_list and not values.get("date"):
            day = self.env.context.get("kpi_hub_date") or self.env.context.get("default_date")
            if day:
                values["date"] = fields.Date.to_date(day)
        if "is_fail" in fields_list and "is_fail" not in values:
            values["is_fail"] = True
        return values

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
        vals_list = [self._prepare_day_entry_vals(vals) for vals in vals_list]
        lines = super().create(vals_list)
        lines._after_change_recompute()
        return lines

    def write(self, vals):
        edit_fields = {"is_fail", "note", "criterion_id", "employee_id"}
        if edit_fields.intersection(vals):
            for line in self:
                line.monthly_employee_id.sheet_id._check_captain_editable()
        if "employee_id" in vals:
            vals = dict(vals)
            employee_id = vals.pop("employee_id")
            if len(self) != 1:
                raise UserError(self.env._("Chỉ sửa nhân viên từng dòng một."))
            sheet = self.sheet_id or self._sheet_from_context()
            vals["monthly_employee_id"] = self._monthly_employee_for(employee_id, sheet).id
        res = super().write(vals)
        if {"is_fail", "note", "criterion_id", "monthly_employee_id"}.intersection(vals):
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

    @api.model
    def action_kpi_add_entry(self):
        """Compatibility hook for list header; inline list uses create=bottom."""
        sheet_id = self.env.context.get("kpi_sheet_id")
        if not sheet_id:
            raise UserError(self.env._("Thiếu thông tin ngày KPI."))
        sheet = self.env["hr.kpi.monthly.sheet"].browse(sheet_id).exists()
        if not sheet:
            raise UserError(self.env._("Không tìm thấy bảng KPI tháng."))
        sheet._check_captain_editable()
        return True