# -*- coding: utf-8 -*-

from odoo import models, fields, api
import re


class ResCompany(models.Model):
    _inherit = 'res.company'

    employee_code_prefix = fields.Char(
        string='Employee Code Prefix',
        size=10,
        help='Prefix for employee codes (e.g., KV, TN, ZM). This will be used to generate unique employee codes per company.'
    )

    def _create_employee_code_sequence(self):
        """Create or update employee code sequence for this company"""
        for company in self:
            if not company.employee_code_prefix:
                continue

            # Validate prefix (alphanumeric, uppercase)
            prefix = company.employee_code_prefix.strip().upper()
            if not re.match(r'^[A-Z0-9]+$', prefix):
                continue

            # Search for existing sequence for this company
            sequence = self.env['ir.sequence'].search([
                ('code', '=', 'hr.employee.emp_code'),
                ('company_id', '=', company.id)
            ], limit=1)

            # Find the highest existing employee code for this company with this prefix
            # to initialize the sequence number_next
            existing_employees = self.env['hr.employee'].search([
                ('company_id', '=', company.id),
                ('emp_code', '!=', False),
                ('emp_code', '=like', f'{prefix}%')
            ])
            
            number_next = 1
            if existing_employees:
                # Extract numeric part from existing codes and find the maximum
                max_num = 0
                for emp in existing_employees:
                    if emp.emp_code and emp.emp_code.startswith(prefix):
                        try:
                            # Extract number after prefix
                            num_str = emp.emp_code[len(prefix):].lstrip('0') or '0'
                            num = int(num_str)
                            max_num = max(max_num, num)
                        except (ValueError, IndexError):
                            continue
                number_next = max_num + 1

            sequence_vals = {
                'name': f'Employee Code ({company.name})',
                'code': 'hr.employee.emp_code',
                'company_id': company.id,
                'prefix': prefix,
                'padding': 4,
                'implementation': 'standard',
                'active': True,
                'number_next': number_next,
            }

            if sequence:
                # Update existing sequence, but preserve number_next if it's higher
                if sequence.number_next < number_next:
                    sequence_vals['number_next'] = number_next
                else:
                    # Don't overwrite if sequence is already ahead
                    sequence_vals.pop('number_next', None)
                sequence.write(sequence_vals)
            else:
                # Create new sequence
                self.env['ir.sequence'].create(sequence_vals)

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to create employee code sequence when prefix is set"""
        companies = super().create(vals_list)
        companies._create_employee_code_sequence()
        return companies

    def write(self, vals):
        """Override write to update employee code sequence when prefix changes"""
        result = super().write(vals)
        if 'employee_code_prefix' in vals:
            self._create_employee_code_sequence()
        return result

    @api.model
    def init_employee_code_sequences(self):
        """Initialize employee code sequences for all existing companies
        This method can be called from Odoo shell or as a scheduled action
        """
        companies = self.search([])
        companies._create_employee_code_sequence()
        return True
