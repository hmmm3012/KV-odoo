# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase

from odoo.addons.hr_employee_kv.models.intro_letter_docx import build_intro_letter_docx
from odoo.addons.hr_employee_kv.models.intro_letter_templates import THANH_NIEN


class TestIntroLetterTemplates(TransactionCase):
    def test_thanh_nien_docx_build(self):
        company = self.env.company
        company.intro_letter_template = THANH_NIEN
        employee = self.env["hr.employee"].create(
            {
                "name": "Nguyễn Văn Test",
                "company_id": company.id,
                "sex": "male",
            }
        )
        wizard = self.env["hr.employee.intro.letter.wizard"].create(
            {
                "employee_id": employee.id,
                "recipient": "BAN QUẢN LÝ DEMO\nBAN QUẢN LÝ BÃI XE",
                "export_format": "docx",
            }
        )
        content = build_intro_letter_docx(wizard)
        self.assertTrue(content)
        self.assertGreater(len(content), 1000)