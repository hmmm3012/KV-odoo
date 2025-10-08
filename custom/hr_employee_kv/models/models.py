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

    # # Departure date
    # departure_date = fields.Date("Ngày nghỉ việc")

    # Date of import
    date_import = fields.Date("Ngày nhận việc")

    # Employee code
    emp_code = fields.Char("Mã nhân viên")

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