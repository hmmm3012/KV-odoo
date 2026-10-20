import logging

from odoo import api, fields, models

from .id_card_ocr import decode_id_card_front, inspect_id_card_front

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
        help="Front of the citizen ID. A decoded QR fills the card fields, and the printed place of origin is added from the card text. If the QR cannot be read, the printed text fills the fields.",
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
            if vals.get("id_card_front"):
                vals.update(self._id_card_qr_updates(vals["id_card_front"], vals))
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
        if vals.get("id_card_front") and not self.env.context.get("skip_id_card_qr"):
            if len(self) == 1:
                vals = dict(vals)
                vals.update(self._id_card_qr_updates(vals["id_card_front"], vals))
            else:
                res = super().write(vals)
                for employee in self:
                    updates = employee._id_card_qr_updates(vals["id_card_front"], vals)
                    if updates:
                        employee.with_context(skip_id_card_qr=True).write(updates)
                return res
        return super().write(vals)

    @api.onchange("id_card_front")
    def _onchange_id_card_front(self):
        if not self.id_card_front:
            return
        parsed, status = inspect_id_card_front(self.id_card_front)
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
                "The front image could not be opened. Upload a JPG or PNG photo of the card."
            ),
        }.get(status, (
            "The printed text on the front of the card could not be read. "
            "The photo is kept; fill in the fields manually."
        ))

    def _id_card_qr_updates(self, image, incoming):
        """QR values for fields this save did not already set."""
        parsed = decode_id_card_front(image)
        if not parsed:
            _logger.warning(
                "CCCD front was not read (employees %s).",
                self.ids or "new",
            )
            return {}
        return {
            field_name: parsed[field_name]
            for field_name in _ID_CARD_QR_FIELDS
            if field_name in parsed and field_name not in incoming
        }
