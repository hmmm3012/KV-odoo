# -*- coding: utf-8 -*-

import base64
from io import BytesIO

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import xlsxwriter


class HrKpiMonthlySheet(models.Model):
    _name = "hr.kpi.monthly.sheet"
    _description = "Bảng KPI tháng"
    _order = "month_date desc, department_id"

    name = fields.Char(compute="_compute_name", store=True)
    department_id = fields.Many2one(
        "hr.department",
        string="Bãi xe",
        required=True,
        index=True,
        ondelete="restrict",
    )
    company_id = fields.Many2one(
        related="department_id.company_id",
        store=True,
        index=True,
    )
    month_date = fields.Date(
        string="Tháng",
        required=True,
        index=True,
        help="Ngày đầu tháng của kỳ KPI.",
    )
    state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("submitted", "Đã gửi"),
            ("locked", "Đã chốt"),
        ],
        default="draft",
        required=True,
    )
    employee_ids = fields.One2many("hr.kpi.monthly.employee", "sheet_id", string="Nhân viên")
    lock_deadline = fields.Date(compute="_compute_lock_deadline", store=True)
    export_file = fields.Binary(attachment=False)
    export_file_name = fields.Char()

    _sql_constraints = [
        (
            "department_month_uniq",
            "unique(department_id, month_date)",
            "Đã có bảng KPI cho bãi xe này trong tháng đó.",
        ),
    ]

    @api.depends("department_id", "month_date")
    def _compute_name(self):
        for sheet in self:
            if sheet.department_id and sheet.month_date:
                sheet.name = "%s — %s" % (
                    sheet.department_id.display_name,
                    sheet.month_date.strftime("%m/%Y"),
                )
            else:
                sheet.name = False

    @api.depends("month_date", "company_id")
    def _compute_lock_deadline(self):
        for sheet in self:
            if not sheet.month_date:
                sheet.lock_deadline = False
                continue
            company = sheet.company_id or self.env.company
            next_month = sheet.month_date + relativedelta(months=1)
            lock_day = min(max(company.kpi_lock_day or 5, 1), 28)
            sheet.lock_deadline = next_month.replace(day=lock_day)

    @api.model
    def _user_is_hr(self):
        user = self.env.user
        return (
            self.env.su
            or user.has_group("hr.group_hr_user")
            or user.has_group("hr_attendance.group_hr_attendance_officer")
            or user.has_group("base.group_system")
        )

    def _check_captain_editable(self):
        self.ensure_one()
        if self.state == "locked" and not self._user_is_hr():
            raise UserError(self.env._("Bảng KPI tháng đã chốt. Chỉ nhân sự được chỉnh sửa."))
        today = fields.Date.context_today(self)
        if self.lock_deadline and today >= self.lock_deadline and not self._user_is_hr():
            raise UserError(self.env._(
                "Đã quá hạn nhập KPI (chốt ngày %(lock)s). Chỉ nhân sự được chỉnh sửa.",
                lock=self.lock_deadline.strftime("%d/%m/%Y"),
            ))

    def _check_department_access(self):
        self.ensure_one()
        self.sudo().department_id.with_user(self.env.user).check_access("read")

    @api.model
    def _department_domain(self):
        if self._user_is_hr():
            return []
        return [("id", "in", self.env.user._hr_site_captain_department_ids())]

    @api.model_create_multi
    def create(self, vals_list):
        sheets = super().create(vals_list)
        for sheet in sheets:
            sheet._check_department_access()
            sheet._ensure_employee_lines()
        return sheets

    def write(self, vals):
        if not self._user_is_hr() and "state" not in vals:
            for sheet in self:
                sheet._check_captain_editable()
        res = super().write(vals)
        if "department_id" in vals or vals.get("month_date"):
            self._ensure_employee_lines()
        return res

    def unlink(self):
        for sheet in self:
            if sheet.state == "locked" and not self._user_is_hr():
                raise UserError(self.env._("Không thể xóa bảng KPI đã chốt."))
            sheet._check_captain_editable()
        return super().unlink()

    def _month_bounds(self):
        self.ensure_one()
        start = self.month_date
        end = start + relativedelta(months=1, days=-1)
        return start, end

    def _ensure_employee_lines(self):
        EmployeeMonth = self.env["hr.kpi.monthly.employee"]
        for sheet in self:
            employees = sheet.department_id.member_ids
            existing = {line.employee_id.id: line for line in sheet.employee_ids}
            for employee in employees:
                if employee.id not in existing:
                    EmployeeMonth.create({
                        "sheet_id": sheet.id,
                        "employee_id": employee.id,
                    })

    def action_submit(self):
        for sheet in self:
            sheet._check_captain_editable()
            sheet._check_department_access()
            sheet.employee_ids.action_recompute()
            sheet.state = "submitted"
        return True

    def action_unlock_draft(self):
        if not self._user_is_hr():
            raise AccessError(self.env._("Chỉ nhân sự được mở khóa bảng KPI."))
        self.write({"state": "draft"})
        return True

    def action_hr_lock(self):
        if not self._user_is_hr():
            raise AccessError(self.env._("Chỉ nhân sự được chốt bảng KPI tháng."))
        for sheet in self:
            sheet.employee_ids.action_recompute()
            sheet.state = "locked"
        return True

    def action_recompute_all(self):
        self._check_captain_editable()
        self.employee_ids.action_recompute()
        return True

    def action_export_xlsx(self):
        self.ensure_one()
        self._check_department_access()
        if not xlsxwriter:
            raise UserError(self.env._("Không xuất được Excel trên máy chủ này."))
        self.employee_ids.action_recompute()
        content = self._render_xlsx()
        filename = "KPI_%s_%s.xlsx" % (
            self.department_id.name.replace(" ", "_"),
            self.month_date.strftime("%m%Y"),
        )
        self.write({
            "export_file": base64.b64encode(content),
            "export_file_name": filename,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content?model=%s&id=%s&field=export_file&filename_field=export_file_name&download=true"
            % (self._name, self.id),
            "target": "download",
        }

    def _render_xlsx(self):
        self.ensure_one()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("TH-KPI")
        bold = workbook.add_format({"bold": True, "border": 1})
        cell = workbook.add_format({"border": 1})
        headers = [
            "Mã NV", "Họ tên",
            "A %", "A mô tả",
            "B %", "B mô tả",
            "C %", "D %", "E %", "F %",
            "Tổng trừ %", "Còn lại %", "Ghi chú",
        ]
        sheet.write(0, 0, self.name or "KPI", bold)
        for col, label in enumerate(headers):
            sheet.write(2, col, label, bold)
        row = 3
        for line in self.employee_ids.sorted(lambda l: (l.employee_id.name or "").casefold()):
            sheet.write(row, 0, line.employee_id.emp_code or "", cell)
            sheet.write(row, 1, line.employee_id.name or "", cell)
            sheet.write(row, 2, line.manual_a_percent or 0, cell)
            sheet.write(row, 3, line.manual_a_note or "", cell)
            sheet.write(row, 4, line.manual_b_percent or 0, cell)
            sheet.write(row, 5, line.manual_b_note or "", cell)
            sheet.write(row, 6, line.group_c_percent or 0, cell)
            sheet.write(row, 7, line.group_d_percent or 0, cell)
            sheet.write(row, 8, line.group_e_percent or 0, cell)
            sheet.write(row, 9, line.group_f_percent or 0, cell)
            sheet.write(row, 10, line.total_deduction_percent or 0, cell)
            sheet.write(row, 11, line.kpi_remaining_percent or 0, cell)
            sheet.write(row, 12, line.note or "", cell)
            row += 1
        workbook.close()
        return output.getvalue()