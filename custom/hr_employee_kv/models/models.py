from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Permanent Address
    emp_permanent_address = fields.Char("Địa chỉ thường trú")

    # Temporary Address
    emp_temporary_address = fields.Char("Địa chỉ tạm trú")

    # Identification date
    identification_date = fields.Date("Ngày cấp")

    # Identification by
    identification_by = fields.Char("Nơi cấp")

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
