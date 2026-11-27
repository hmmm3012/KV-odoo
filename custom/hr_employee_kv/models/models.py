import logging
from datetime import date, datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

from .id_card_ocr import inspect_id_card

_logger = logging.getLogger(__name__)

# Odoo 19 renamed hr.employee.gender -> sex (now stored on hr.version).
# The CCCD parsers still return "gender"; _id_card_fields() maps it.
_ID_CARD_QR_FIELDS = (
    "name",
    "identification_id",
    "birthday",
    "sex",
    "emp_permanent_address",
    "emp_temporary_address",
    "emp_place_of_origin",
    "identification_date",
    "identification_by",
)

# Sentinel from the form widget: use the photo already stored on the employee.
_FROM_RECORD = "FROM_RECORD"


def _id_card_fields(parsed):
    """Map CCCD parser keys to Odoo 19 field names."""
    parsed = dict(parsed or {})
    if "gender" in parsed:
        parsed["sex"] = parsed.pop("gender")
    return parsed


def _serialize_id_card_values(parsed):
    """JSON-safe field values for the form widget / RPC."""
    values = {}
    for field_name, value in _id_card_fields(parsed).items():
        if field_name not in _ID_CARD_QR_FIELDS:
            continue
        if isinstance(value, date):
            values[field_name] = value.isoformat()
        else:
            values[field_name] = value
    return values


class HrVersion(models.Model):
    """Odoo 19 moved country_id / departure_date from hr.employee to
    hr.version (hr.employee _inherits hr.version). Override them there so
    the employee does not get shadow columns."""

    _inherit = "hr.version"

    # Default nationality Vietnam, read-only on the form
    country_id = fields.Many2one(
        string="Nationality (Country)",
        default=lambda self: self.env.ref("base.vn", False),
        readonly=True,
    )

    departure_date = fields.Date(string="Ngày nghỉ việc")


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Permanent Address
    emp_permanent_address = fields.Char("Địa chỉ thường trú")
    emp_place_of_origin = fields.Char("Quê quán")

    # Temporary Address
    emp_temporary_address = fields.Char("Địa chỉ tạm trú")

    # Identification date
    identification_date = fields.Date("Ngày cấp")

    # Identification by
    identification_by = fields.Char("Nơi cấp")

    id_card_front = fields.Image(
        string="CCCD mặt trước",
        max_width=1920,
        max_height=1920,
        copy=False,
        groups="hr.group_hr_user",
        help="Ảnh mặt trước CCCD. Sau khi tải ảnh lên, bấm Tự nhập thông tin để đọc mã QR hoặc chữ in trên thẻ. Quê quán in trên CCCD được đọc từ ảnh này.",
    )
    id_card_back = fields.Image(
        string="CCCD mặt sau",
        max_width=1920,
        max_height=1920,
        copy=False,
        groups="hr.group_hr_user",
        help="Ảnh mặt sau CCCD. Dùng khi mã QR nằm ở mặt sau thay vì mặt trước. Sau khi tải ảnh lên, bấm Tự nhập thông tin để bắt đầu đọc.",
    )

    # Date of import
    date_import = fields.Date("Ngày nhận việc")

    # HR source
    emp_hr_source = fields.Selection(
        [
            ("internal_referral", "Nội bộ giới thiệu"),
            ("hr_recruitment", "Phòng nhân sự tuyển dụng"),
            ("other_parking_referral", "Bãi xe khác giới thiệu"),
        ],
        string="Nguồn nhân sự",
    )

    # Employee code - generated automatically via ir.sequence in create()
    emp_code = fields.Char("Mã nhân viên", readonly=True, copy=False)

    # Tax identification number
    tax_identification_number = fields.Char("MST")

    # Notes
    notes = fields.Text("Ghi chú")

    # SINID
    sinid = fields.Char("Mã bảo hiểm")

    # Fire safety (PCCC) certificate
    fire_safety_cert_date = fields.Date("Chứng chỉ PCCC (ngày cấp)")
    
    # Month of birth - computed field based on birthday
    month_of_birth = fields.Selection(
        [(str(i), str(i)) for i in range(1, 13)],
        string="Tháng sinh",
        compute='_compute_month_of_birth',
        store=True
    )
    
    @api.depends('birthday')
    def _compute_month_of_birth(self):
        """Compute month of birth based on birthday field"""
        for record in self:
            if record.birthday:
                record.month_of_birth = str(record.birthday.month)
            else:
                record.month_of_birth = False

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to assign emp_code using company-specific ir.sequence"""
        IrSequence = self.env['ir.sequence'].sudo()
        for vals in vals_list:
            # Only assign emp_code if not already provided
            if not vals.get('emp_code'):
                # Get company_id from vals or use current company
                company_id = vals.get('company_id') or self.env.company.id
                company = self.env['res.company'].browse(company_id)

                if not company.exists():
                    vals['emp_code'] = False
                    continue

                # Search with sudo() so record rules don't hide the sequence
                sequence = IrSequence.search([
                    ('code', '=', 'hr.employee.emp_code'),
                    ('company_id', '=', company.id)
                ], limit=1)

                if not sequence:
                    # Try to create sequence if company has prefix set
                    if company.employee_code_prefix:
                        company.sudo()._create_employee_code_sequence()
                        sequence = IrSequence.search([
                            ('code', '=', 'hr.employee.emp_code'),
                            ('company_id', '=', company.id)
                        ], limit=1)

                if sequence:
                    # Use the sequence directly to get next number (sudo for _next)
                    emp_code = sequence._next()
                else:
                    emp_code = False

                vals['emp_code'] = emp_code or False
        return super().create(vals_list)

    def _id_card_user_feedback(self, status, values):
        """Vietnamese notification for the Tự nhập thông tin button."""
        if status == "qr":
            message = "Đã đọc thông tin từ mã QR trên ảnh CCCD."
            if values.get("emp_place_of_origin"):
                message += " Quê quán được bổ sung từ chữ in trên thẻ."
            return "success", message
        if status == "ocr":
            return (
                "success",
                "Không đọc được mã QR, đã nhập thông tin từ chữ in trên ảnh CCCD (OCR).",
            )
        if status == "empty":
            return (
                "warning",
                "Chưa có ảnh CCCD. Hãy tải lên ảnh mặt trước hoặc mặt sau rồi bấm Tự nhập thông tin.",
            )
        if status == "unreadable":
            return (
                "warning",
                "Không mở được ảnh CCCD. Hãy tải lên ảnh JPG, PNG hoặc WebP rõ nét.",
            )
        return (
            "warning",
            "Không đọc được mã QR hoặc chữ in trên ảnh CCCD. Ảnh vẫn được giữ lại, hãy nhập tay các trường thông tin.",
        )

    def _resolve_id_card_images(self, front, back, employee_id=None):
        record = self.browse(employee_id) if employee_id else self[:1]
        if record:
            record = record.exists().with_context(bin_size=False)
        if front == _FROM_RECORD:
            front = record.id_card_front if record else False
        if back == _FROM_RECORD:
            back = record.id_card_back if record else False
        return front, back

    @api.model
    def read_id_card_from_images(self, front=None, back=None, employee_id=False):
        """Read QR (then OCR) from CCCD photos without writing the employee.

        Called by the Tự nhập thông tin form widget so it also works on a
        new, unsaved employee. Dates are returned as ISO strings.
        """
        front, back = self._resolve_id_card_images(front, back, employee_id)
        prefer = "back" if back and not front else "front"
        parsed, status = inspect_id_card(front, back, prefer=prefer)
        values = _serialize_id_card_values(parsed)
        notification_type, message = self._id_card_user_feedback(status, values)
        return {
            "ok": bool(values),
            "source": status if status in ("qr", "ocr") else False,
            "status": status,
            "values": values,
            "title": "Tự nhập thông tin",
            "message": message,
            "notification_type": notification_type,
        }

    def action_fill_from_id_card(self):
        """Fill this employee from stored CCCD photos (tests / fallback)."""
        self.ensure_one()
        result = self.read_id_card_from_images(
            front=_FROM_RECORD if self.id_card_front else False,
            back=_FROM_RECORD if self.id_card_back else False,
            employee_id=self.id,
        )
        if result["status"] == "empty":
            raise UserError(result["message"])
        if result["values"]:
            write_vals = dict(result["values"])
            for field_name in ("birthday", "identification_date"):
                raw = write_vals.get(field_name)
                if raw and isinstance(raw, str):
                    write_vals[field_name] = datetime.strptime(raw, "%Y-%m-%d").date()
            self.write(write_vals)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": result["title"],
                "message": result["message"],
                "type": result["notification_type"],
                "sticky": False,
            },
        }
