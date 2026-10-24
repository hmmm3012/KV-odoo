import logging

from odoo import api, fields, models

from .id_card_ocr import decode_id_card, inspect_id_card

_logger = logging.getLogger(__name__)

_ID_CARD_QR_FIELDS = (
    "name",
    "identification_id",
    "birthday",
    "gender",
    "emp_permanent_address",
    "emp_temporary_address",
    "emp_place_of_origin",
    "identification_date",
    "identification_by",
)


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
        help="Front of the citizen ID. The QR on either side fills the card fields. Printed place of origin is read from this photo.",
    )
    id_card_back = fields.Image(
        string="CCCD mặt sau",
        max_width=1920,
        max_height=1920,
        copy=False,
        groups="hr.group_hr_user",
        help="Back of the citizen ID. Used when the QR is on this side instead of the front.",
    )

    # Override country_id to set default to Vietnam and make readonly
    country_id = fields.Many2one('res.country', 'Nationality (Country)', 
                                default=lambda self: self.env.ref('base.vn', False),
                                readonly=True)

    # Departure date
    departure_date = fields.Date("Ngày nghỉ việc")

    # Date of import
    date_import = fields.Date("Ngày nhận việc")

    # Employee code - generated automatically via ir.sequence in create()
    emp_code = fields.Char("Mã nhân viên", readonly=True, copy=False)

    # Tax identification number
    tax_identification_number = fields.Char("MST")

    # Notes
    notes = fields.Text("Ghi chú")

    # SINID
    sinid = fields.Char("Mã bảo hiểm")
    
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
            if vals.get("id_card_front") or vals.get("id_card_back"):
                vals.update(self._id_card_qr_updates(vals))
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

    def write(self, vals):
        if (
            (vals.get("id_card_front") or vals.get("id_card_back"))
            and not self.env.context.get("skip_id_card_qr")
        ):
            if len(self) == 1:
                vals = dict(vals)
                vals.update(self._id_card_qr_updates(vals))
            else:
                res = super().write(vals)
                for employee in self:
                    updates = employee._id_card_qr_updates(vals)
                    if updates:
                        employee.with_context(skip_id_card_qr=True).write(updates)
                return res
        return super().write(vals)

    @api.onchange("id_card_front", "id_card_back")
    def _onchange_id_card_images(self):
        if not self.id_card_front and not self.id_card_back:
            return
        parsed, status = inspect_id_card(
            self.id_card_front,
            self.id_card_back,
            prefer="back" if self.id_card_back and not self.id_card_front else "front",
        )
        if not parsed:
            return {
                "warning": {
                    "title": self.env._("CCCD"),
                    "message": self.env._(self._id_card_qr_warning(status)),
                }
            }
        for field_name, value in parsed.items():
            self[field_name] = value

    @api.model
    def _id_card_qr_warning(self, status):
        return {
            "unreadable": (
                "The ID card image could not be opened. Upload a JPG or PNG photo of the card."
            ),
        }.get(status, (
            "No QR code or printed card text could be read on either side. "
            "The photo is kept; fill in the fields manually."
        ))

    def _id_card_images(self, incoming):
        front = incoming.get("id_card_front")
        back = incoming.get("id_card_back")
        record = self[:1]
        if "id_card_front" not in incoming and record:
            front = record.with_context(bin_size=False).id_card_front
        if "id_card_back" not in incoming and record:
            back = record.with_context(bin_size=False).id_card_back
        return front, back

    def _id_card_qr_updates(self, incoming):
        """QR/OCR values for fields this save did not already set."""
        front, back = self._id_card_images(incoming)
        prefer = "back" if incoming.get("id_card_back") and not incoming.get("id_card_front") else "front"
        parsed = decode_id_card(front, back, prefer=prefer)
        if not parsed:
            _logger.warning(
                "CCCD was not read (employees %s).",
                self.ids or "new",
            )
            return {}
        return {
            field_name: parsed[field_name]
            for field_name in _ID_CARD_QR_FIELDS
            if field_name in parsed and field_name not in incoming
        }
