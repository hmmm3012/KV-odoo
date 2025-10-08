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

    @api.model
    def _get_default_emp_code(self):
        """Default value for emp_code field"""
        try:
            company_id = self.env.company.id
            code = self._get_next_employee_code(company_id)
            return code
        except Exception as e:
            return f"EMP{self.env.company.id}0001"
    
    # Employee code
    emp_code = fields.Char("Mã nhân viên", default=_get_default_emp_code)

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


    def _get_next_employee_code(self, company_id):
        """Generate the next employee code for the given company.
        
        Args:
            company_id (int): Company ID to generate code for
            
        Returns:
            str: The next employee code in format 'KV123456'
        """
        try:
            # Find the latest employee code for this company
            latest_employee = self.search([
                ('company_id', '=', company_id),
                ('emp_code', '!=', False)
            ], order='emp_code desc', limit=1)

            if latest_employee and latest_employee.emp_code:
                latest_code = latest_employee.emp_code
                
                # Extract prefix and number from the latest code
                # Split the code into letters (prefix) and numbers
                import re
                match = re.match(r'^([A-Za-z]+)(\d+)$', latest_code)
                
                if match:
                    prefix = match.group(1)  # Extract letters part
                    number_part = match.group(2)  # Extract numbers part
                    try:
                        next_number = int(number_part) + 1
                    except ValueError:
                        next_number = 1
                else:
                    # If format doesn't match, use default prefix
                    prefix = "KV"
                    next_number = 1
            else:
                # No existing employees, use default prefix and start from 1
                prefix = "KV"
                next_number = 1
            
            # Format the new employee code
            result = f"{prefix}{next_number}"
            return result
        except Exception as e:
            # Fallback to a simple code
            return f"KV{company_id}{len(self.search([])) + 1:04d}"
