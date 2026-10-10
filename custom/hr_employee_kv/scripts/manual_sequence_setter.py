#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual script to check and set employee code sequence number_next for companies.
Run this in Odoo shell: ./odoo-bin -c config/odoo.conf shell -d odoo
Then paste the functions you need.
"""

def check_all_sequences():
    """Check current sequence status for all companies"""
    Company = env['res.company']
    Sequence = env['ir.sequence'].sudo()
    Employee = env['hr.employee']
    
    print("\n=== Employee Code Sequence Status ===\n")
    
    for company in Company.search([]):
        prefix = (company.employee_code_prefix or '').strip().upper()
        if not prefix:
            print(f"Company: {company.name} - No prefix set")
            continue
        
        # Find sequence
        seq = Sequence.search([
            ('code', '=', 'hr.employee.emp_code'),
            ('company_id', '=', company.id),
        ], limit=1)
        
        # Find max existing code
        employees = Employee.search([
            ('company_id', '=', company.id),
            ('emp_code', '!=', False),
            ('emp_code', '=like', f'{prefix}%'),
        ])
        
        max_num = 0
        max_code = None
        for emp in employees:
            code = emp.emp_code or ''
            if code.startswith(prefix):
                try:
                    num_str = code[len(prefix):].lstrip('0') or '0'
                    num = int(num_str)
                    if num > max_num:
                        max_num = num
                        max_code = code
                except ValueError:
                    pass
        
        if seq:
            print(f"Company: {company.name} (ID: {company.id})")
            print(f"  Prefix: {prefix}")
            print(f"  Sequence number_next: {seq.number_next}")
            print(f"  Max existing code: {max_code or 'None'} (number: {max_num})")
            print(f"  Next code will be: {prefix}{seq.number_next:04d}")
            if seq.number_next <= max_num:
                print(f"  ⚠️  WARNING: Sequence is behind! Should be at least {max_num + 1}")
            print()
        else:
            print(f"Company: {company.name} (ID: {company.id})")
            print(f"  Prefix: {prefix}")
            print(f"  ⚠️  No sequence found! Max existing: {max_code or 'None'}")
            print()


def set_sequence_for_company(company_id, next_number):
    """Manually set sequence number_next for a specific company
    
    Args:
        company_id: ID of the company
        next_number: The next number to use (e.g., if latest is KV0005, set to 6)
    
    Example:
        set_sequence_for_company(1, 6)  # Set company ID 1 to start from 6
    """
    Company = env['res.company']
    Sequence = env['ir.sequence'].sudo()
    
    company = Company.browse(company_id)
    if not company.exists():
        print(f"Company ID {company_id} not found!")
        return False
    
    prefix = (company.employee_code_prefix or '').strip().upper()
    if not prefix:
        print(f"Company {company.name} has no prefix set!")
        return False
    
    seq = Sequence.search([
        ('code', '=', 'hr.employee.emp_code'),
        ('company_id', '=', company.id),
    ], limit=1)
    
    if not seq:
        print(f"No sequence found for company {company.name}. Creating one...")
        seq = Sequence.create({
            'name': f'Employee Code ({company.name})',
            'code': 'hr.employee.emp_code',
            'company_id': company.id,
            'prefix': prefix,
            'padding': 4,
            'implementation': 'standard',
            'active': True,
            'number_next': next_number,
        })
        print(f"✓ Created sequence with number_next = {next_number}")
    else:
        seq.write({'number_next': next_number})
        print(f"✓ Updated sequence for {company.name} to number_next = {next_number}")
        print(f"  Next employee code will be: {prefix}{next_number:04d}")
    
    return True


def auto_fix_all_sequences():
    """Automatically fix all sequences to continue from existing codes"""
    Company = env['res.company']
    Employee = env['hr.employee']
    Sequence = env['ir.sequence'].sudo()
    
    print("\n=== Auto-fixing sequences ===\n")
    
    for company in Company.search([]):
        prefix = (company.employee_code_prefix or '').strip().upper()
        if not prefix:
            continue
        
        # Find max existing code
        employees = Employee.search([
            ('company_id', '=', company.id),
            ('emp_code', '!=', False),
            ('emp_code', '=like', f'{prefix}%'),
        ])
        
        max_num = 0
        for emp in employees:
            code = emp.emp_code or ''
            if code.startswith(prefix):
                try:
                    num_str = code[len(prefix):].lstrip('0') or '0'
                    num = int(num_str)
                    max_num = max(max_num, num)
                except ValueError:
                    pass
        
        next_num = max_num + 1 if max_num else 1
        
        seq = Sequence.search([
            ('code', '=', 'hr.employee.emp_code'),
            ('company_id', '=', company.id),
        ], limit=1)
        
        if seq:
            if seq.number_next < next_num:
                seq.write({'number_next': next_num})
                print(f"✓ Fixed {company.name}: → {next_num} (next: {prefix}{next_num:04d})")
            else:
                print(f"  {company.name}: Already correct ({seq.number_next}, next: {prefix}{seq.number_next:04d})")
        else:
            Sequence.create({
                'name': f'Employee Code ({company.name})',
                'code': 'hr.employee.emp_code',
                'company_id': company.id,
                'prefix': prefix,
                'padding': 4,
                'implementation': 'standard',
                'active': True,
                'number_next': next_num,
            })
            print(f"✓ Created sequence for {company.name}: next = {next_num} ({prefix}{next_num:04d})")
    
    print("\n✓ Done! Run: env.cr.commit()  to persist changes.")


# Usage examples (run in Odoo shell):
# 
# 1. Check all sequences:
#    check_all_sequences()
#
# 2. Manually set for a specific company:
#    set_sequence_for_company(1, 6)  # Company ID 1, start from 6
#
# 3. Auto-fix all sequences:
#    auto_fix_all_sequences()
