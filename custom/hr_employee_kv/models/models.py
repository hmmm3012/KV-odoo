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