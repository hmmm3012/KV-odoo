# -*- coding: utf-8 -*-

import base64

from odoo import api, fields, models
from odoo.exceptions import UserError

from .intro_letter_docx import build_intro_letter_docx
from .intro_letter_odt import export_intro_letter_pdf_from_odt

HEALTH_STATUS_DEFAULT = "đủ sức khoẻ làm việc"
PROP_WORK_SHIFT = "Ca làm việc"
PROP_EDUCATION = "Học vấn"


class HrEmployeeIntroLetterWizard(models.TransientModel):
    _name = "hr.employee.intro.letter.wizard"
    _description = "Giấy giới thiệu nhân sự"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Nhân viên",
        required=True,
        readonly=True,
    )
    recipient = fields.Char(string="Kính gửi", required=True)
    # Company employee Properties (not standard Education / Working Hours).
    education_level = fields.Char(
        string="Học vấn",
        compute="_compute_employee_property_fields",
        readonly=True,
    )
    work_shift = fields.Char(
        string="Ca làm việc",
        compute="_compute_employee_property_fields",
        readonly=True,
    )
    export_format = fields.Selection(
        [
            ("docx", "Word (.docx)"),
            ("pdf", "PDF"),
        ],
        string="Định dạng",
        required=True,
        default="docx",
    )
    file_data = fields.Binary(string="File", readonly=True, attachment=False)
    file_name = fields.Char(string="Tên file", readonly=True)

    @api.depends("employee_id", "employee_id.employee_properties")
    def _compute_employee_property_fields(self):
        for wizard in self:
            wizard.education_level = wizard._employee_property_display(PROP_EDUCATION)
            wizard.work_shift = wizard._employee_property_display(PROP_WORK_SHIFT)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        employee = self.env["hr.employee"].browse(self.env.context.get("active_id"))
        if employee:
            values.setdefault("employee_id", employee.id)
        values.setdefault("export_format", "docx")
        return values

    def action_download(self):
        self.ensure_one()
        if not self.employee_id:
            raise UserError(self.env._("Không tìm thấy nhân viên."))
        if self.export_format == "docx":
            content = build_intro_letter_docx(self)
            extension = "docx"
        else:
            content = export_intro_letter_pdf_from_odt(self)
            extension = "pdf"
        return self._action_download_file(content, extension)

    def _action_download_file(self, content, extension):
        self.ensure_one()
        filename = self._download_filename(extension)
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

    def _download_filename(self, extension):
        self.ensure_one()
        code = (self.employee_id.emp_code or "NV").replace("/", "-")
        return f"Giay_gioi_thieu_{code}.{extension}"

    def _format_date(self, value):
        if not value:
            return ""
        if isinstance(value, str):
            value = fields.Date.to_date(value)
        return value.strftime("%d/%m/%Y")

    def _phone(self):
        employee = self.employee_id
        return employee.private_phone or employee.mobile_phone or employee.work_phone or ""

    def _employee_property_definition(self, label):
        """Find a company employee Property definition by its display string."""
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return None
        definitions = employee.company_id.employee_properties_definition or []
        for definition in definitions:
            if definition.get("string") == label:
                return definition
        return None

    def _employee_property_display(self, label):
        """Resolve Properties value (selection → label, char → text)."""
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return ""
        definition = self._employee_property_definition(label)
        if not definition:
            return ""
        props = employee.employee_properties or {}
        raw = props.get(definition.get("name"))
        if not raw:
            return ""
        if definition.get("type") == "selection":
            options = {
                option[0]: option[1]
                for option in (definition.get("selection") or [])
                if option
            }
            return options.get(raw, raw) or ""
        return str(raw).strip()

    @api.model
    def _province_from_address(self, address):
        """Keep only the province/city: last comma-separated part.

        Example: "Cổ Bi, Gia Lâm, Hà Nội" -> "Hà Nội"
        """
        if not address:
            return ""
        text = " ".join(str(address).replace("\n", " ").split()).strip(" ,;")
        if not text:
            return ""
        parts = [part.strip(" ,;") for part in text.split(",") if part.strip(" ,;")]
        return parts[-1] if parts else text

    def _letter_values(self):
        """Shared payload for PDF and DOCX renderers."""
        self.ensure_one()
        employee = self.employee_id
        today = fields.Date.context_today(self)
        if isinstance(today, str):
            today = fields.Date.to_date(today)
        return {
            "recipient": self.recipient or "",
            "name": employee.name or "",
            "gender": employee.gender or "",
            "birthday": self._format_date(employee.birthday),
            "place_of_origin": self._province_from_address(
                employee.emp_place_of_origin
            ),
            "identification_id": employee.identification_id or "",
            "identification_date": self._format_date(employee.identification_date),
            "identification_by": employee.identification_by or "",
            "education_level": self.education_level or "",
            "permanent_address": employee.emp_permanent_address or "",
            "temporary_address": employee.emp_temporary_address or "",
            "phone": self._phone(),
            "date_import": self._format_date(employee.date_import),
            "job_title": employee.job_id.name or employee.job_title or "",
            "emp_code": employee.emp_code or "",
            "work_shift": self.work_shift or "",
            "health_status": HEALTH_STATUS_DEFAULT,
            "sign_day": f"{today.day:02d}",
            "sign_month": f"{today.month:02d}",
            "sign_year": str(today.year),
        }
