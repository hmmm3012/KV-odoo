# -*- coding: utf-8 -*-

import base64
from io import BytesIO

from pdfrw import PdfReader
from PIL import Image

from odoo.addons.hr_employee_kv.models.badge_pdf import _TEMPLATE_PDF
from odoo.tests.common import TransactionCase, tagged


def _png(width, height):
    buffer = BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue())


@tagged("post_install", "-at_install")
class TestEmployeeBadge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        department = cls.env["hr.department"].create({"name": "Phòng Nghiệp vụ và đào tạo"})
        job = cls.env["hr.job"].create({"name": "Nhân viên nghiệp vụ"})
        cls.employees = cls.env["hr.employee"].create(
            [
                {
                    "name": "Hà Quang Lý Hùng",
                    "department_id": department.id,
                    "job_id": job.id,
                    "image_1920": _png(600, 800),
                },
                {"name": "Nguyễn Thị Minh", "image_1920": _png(900, 500)},
            ]
            + [
                {"name": f"Nhân viên {index}", "image_1920": _png(400, 500)}
                for index in range(7)
            ]
        )

    def _wizard(self, employees):
        return (
            self.env["hr.employee.badge.wizard"]
            .with_context(active_model="hr.employee", active_ids=employees.ids)
            .create({})
        )

    def _pdf(self, wizard):
        action = wizard.action_print()
        self.assertEqual(action["type"], "ir.actions.act_url")
        return PdfReader(fdata=base64.b64decode(wizard.file_data))

    def test_default_lines(self):
        wizard = self._wizard(self.employees[0])
        line = wizard.line_ids
        self.assertEqual(line.employee_id, self.employees[0])
        self.assertEqual(line.card_name, "HÀ QUANG LÝ HÙNG")
        self.assertEqual(line.job_name, "Nhân viên nghiệp vụ")
        self.assertEqual(line.department_name, "Phòng Nghiệp vụ và đào tạo")

    def test_template_is_100x70mm(self):
        page = PdfReader(str(_TEMPLATE_PDF)).pages[0]
        width = float(page.MediaBox[2]) / 72 * 25.4
        height = float(page.MediaBox[3]) / 72 * 25.4
        self.assertAlmostEqual(width, 100.0, places=2)
        self.assertAlmostEqual(height, 70.0, places=2)

    def test_print_single_uses_edited_name(self):
        wizard = self._wizard(self.employees[0])
        wizard.line_ids.card_name = "HÀ Q. LÝ HÙNG"
        pdf = self._pdf(wizard)
        self.assertEqual(len(pdf.pages), 1)
        self.assertEqual(
            [round(float(v), 1) for v in pdf.pages[0].MediaBox],
            [0, 0, 595.3, 841.9],
        )
        code = (self.employees[0].emp_code or "NV").replace("/", "-")
        self.assertEqual(wizard.file_name, f"The_NV_{code}.pdf")

    def test_print_batch_packs_eight_per_a4(self):
        two = self.employees[:2]
        wizard = self._wizard(two)
        self.assertEqual(len(wizard.line_ids), 2)
        pdf = self._pdf(wizard)
        self.assertEqual(len(pdf.pages), 1)
        self.assertEqual(wizard.file_name, "The_NV_2_nhan_vien.pdf")

        nine = self.employees[:9]
        wizard = self._wizard(nine)
        self.assertEqual(len(wizard.line_ids), 9)
        pdf = self._pdf(wizard)
        self.assertEqual(len(pdf.pages), 2)
        self.assertEqual(wizard.file_name, "The_NV_9_nhan_vien.pdf")
