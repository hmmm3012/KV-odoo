# -*- coding: utf-8 -*-

import base64

from odoo import api, fields, models
from odoo.exceptions import UserError

from .badge_pdf import build_badge_pdf


class HrEmployeeBadgeWizard(models.TransientModel):
    _name = "hr.employee.badge.wizard"
    _description = "In thẻ nhân viên"

    line_ids = fields.One2many(
        "hr.employee.badge.wizard.line",
        "wizard_id",
        string="Nhân viên",
    )
    file_data = fields.Binary(string="File", readonly=True, attachment=False)
    file_name = fields.Char(string="Tên file", readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        context = self.env.context
        if context.get("active_model") == "hr.employee":
            employee_ids = context.get("active_ids") or [context.get("active_id")]
            employees = self.env["hr.employee"].browse([i for i in employee_ids if i])
            values["line_ids"] = [
                fields.Command.create(
                    {
                        "employee_id": employee.id,
                        "card_name": (employee.name or "").upper(),
                    }
                )
                for employee in employees
            ]
        return values

    def action_print(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._("Chưa chọn nhân viên nào để in thẻ."))
        cards = [line._card_values() for line in self.line_ids]
        content = build_badge_pdf(cards)
        filename = self._download_filename()
        self.write(
            {
                "file_data": base64.b64encode(content),
                "file_name": filename,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content?"
                f"model={self._name}&id={self.id}"
                "&field=file_data&filename_field=file_name"
                f"&filename={filename}&download=true"
            ),
            "target": "self",
        }

    def _download_filename(self):
        self.ensure_one()
        if len(self.line_ids) == 1:
            code = (self.line_ids.emp_code or "NV").replace("/", "-")
            return f"The_NV_{code}.pdf"
        return f"The_NV_{len(self.line_ids)}_nhan_vien.pdf"


class HrEmployeeBadgeWizardLine(models.TransientModel):
    _name = "hr.employee.badge.wizard.line"
    _description = "Dòng in thẻ nhân viên"

    wizard_id = fields.Many2one(
        "hr.employee.badge.wizard",
        required=True,
        ondelete="cascade",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Nhân viên",
        required=True,
        readonly=True,
    )
    card_name = fields.Char(string="Họ tên trên thẻ", required=True)
    job_name = fields.Char(string="Chức vụ", compute="_compute_card_info")
    department_name = fields.Char(string="Bộ phận", compute="_compute_card_info")
    emp_code = fields.Char(related="employee_id.emp_code", string="Mã NV")

    @api.depends("employee_id")
    def _compute_card_info(self):
        for line in self:
            employee = line.employee_id
            line.job_name = employee.job_id.name or employee.job_title or ""
            line.department_name = employee.department_id.name or ""

    def _card_values(self):
        self.ensure_one()
        employee = self.employee_id.with_context(bin_size=False)
        return {
            "name": self.card_name,
            "job": self.job_name,
            "department": self.department_name,
            "code": self.emp_code or "",
            "photo": employee.image_1920,
        }
