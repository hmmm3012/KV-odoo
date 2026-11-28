# -*- coding: utf-8 -*-
"""Contract numbering HD.YYYY.NNN on hr.version (Odoo 19).

Numbers are not hard-coded: they depend on whatever is already in the DB.
"""
import re
from datetime import date

from odoo.tests.common import TransactionCase, tagged

HD = re.compile(r"^HD\.\d+\.\d+$")


@tagged("post_install", "-at_install")
class TestContractAutonumber(TransactionCase):
    def test_new_employee_without_contract_start_has_no_hd_number(self):
        employee = self.env["hr.employee"].create({"name": "KV TEST AUTONUMBER A"})
        self.assertFalse(HD.match(employee.version_id.name or ""))

    def test_setting_contract_start_assigns_hd_number(self):
        employee = self.env["hr.employee"].create({"name": "KV TEST AUTONUMBER B"})
        employee.write({
            "contract_date_start": date(2026, 1, 1),
            "contract_date_end": date(2026, 12, 31),
            "wage": 5_000_000,
        })
        self.assertRegex(employee.version_id.name or "", r"^HD\.2026\.\d+$")

    def test_salary_change_keeps_same_number(self):
        employee = self.env["hr.employee"].create({"name": "KV TEST AUTONUMBER C"})
        employee.write({
            "contract_date_start": date(2026, 1, 1),
            "contract_date_end": date(2026, 12, 31),
            "wage": 5_000_000,
        })
        first = employee.version_id
        number = first.name
        second = employee.create_version({"date_version": date(2026, 6, 1), "wage": 6_000_000})
        self.assertNotEqual(second.id, first.id)
        self.assertEqual(second.name, number)
        self.assertEqual(second.contract_date_start, date(2026, 1, 1))

    def test_renewal_gets_a_new_number(self):
        employee = self.env["hr.employee"].create({"name": "KV TEST AUTONUMBER D"})
        employee.write({
            "contract_date_start": date(2026, 1, 1),
            "contract_date_end": date(2026, 12, 31),
            "wage": 5_000_000,
        })
        first = employee.version_id
        old_number = first.name
        renewed = employee.create_version({
            "date_version": date(2027, 1, 1),
            "contract_date_start": date(2027, 1, 1),
            "contract_date_end": date(2027, 12, 31),
        })
        self.assertRegex(renewed.name or "", r"^HD\.\d+\.\d+$")
        self.assertNotEqual(renewed.name, old_number)
        self.assertEqual(first.name, old_number)

    def test_manual_number_is_kept(self):
        employee = self.env["hr.employee"].create({"name": "KV TEST MANUAL"})
        employee.version_id.write({
            "name": "HD.2026.900",
            "contract_date_start": date(2026, 2, 1),
        })
        self.assertEqual(employee.version_id.name, "HD.2026.900")

    def test_batch_create_gets_distinct_numbers(self):
        first, second = self.env["hr.employee"].create([
            {"name": "KV TEST BATCH 1"},
            {"name": "KV TEST BATCH 2"},
        ])
        versions = self.env["hr.version"].create([
            {
                "employee_id": first.id,
                "date_version": date(2026, 3, 1),
                "contract_date_start": date(2026, 3, 1),
            },
            {
                "employee_id": second.id,
                "date_version": date(2026, 3, 1),
                "contract_date_start": date(2026, 3, 1),
            },
        ])
        names = versions.mapped("name")
        self.assertEqual(len(names), 2)
        self.assertTrue(all(HD.match(n or "") for n in names))
        self.assertEqual(len(set(names)), 2)


    def test_print_action_points_at_pdf_route(self):
        """The print button targets /contracts/pdf/<id>."""
        employee = self.env["hr.employee"].create({"name": "KV TEST PDF"})
        employee.write({
            "contract_date_start": date(2026, 1, 1),
            "contract_date_end": date(2026, 12, 31),
            "wage": 5_000_000,
        })
        action = employee.action_kv_print_contract()
        self.assertEqual(action.get("type"), "ir.actions.act_url")
        self.assertIn(f"/contracts/pdf/{employee.version_id.id}", action.get("url") or "")


    def _create_contract_employee(self, name, **vals):
        employee = self.env["hr.employee"].create({"name": name})
        payload = {
            "contract_date_start": date(2026, 1, 1),
            "contract_date_end": date(2026, 12, 31),
            "wage": 5_000_000,
        }
        payload.update(vals)
        employee.write(payload)
        return employee

    def test_create_pdf_with_missing_optional_dates(self):
        """Sparse records (no birthday / ID issue date) must still yield a PDF."""
        from odoo.addons.kv_hr_contract.models.kv_pdf_contract_controller import (
            create_pdf,
        )

        employee = self._create_contract_employee("KV TEST PDF SPARSE")
        pdf = create_pdf(employee.version_id)
        self.assertTrue(pdf.startswith(b"%PDF"), "expected a PDF header")
        self.assertGreater(len(pdf), 1000)

    def test_create_pdf_with_indefinite_contract_and_full_id(self):
        from odoo.addons.kv_hr_contract.models.kv_pdf_contract_controller import (
            create_pdf,
        )

        employee = self._create_contract_employee(
            "KV TEST PDF FULL",
            contract_date_end=False,
            birthday=date(1990, 5, 20),
            identification_id="001234567890",
            identification_date=date(2015, 3, 15),
            identification_by="Cuc Canh Sat",
            emp_permanent_address="1 Le Loi",
            emp_temporary_address="2 Nguyen Hue",
        )
        pdf = create_pdf(employee.version_id)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_create_pdf_without_contract_start_does_not_crash(self):
        from odoo.addons.kv_hr_contract.models.kv_pdf_contract_controller import (
            create_pdf,
        )

        employee = self.env["hr.employee"].create({"name": "KV TEST PDF NO START"})
        pdf = create_pdf(employee.version_id)
        self.assertTrue(pdf.startswith(b"%PDF"))

