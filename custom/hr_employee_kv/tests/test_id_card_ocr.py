# -*- coding: utf-8 -*-

from datetime import date
from pathlib import Path

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.hr_employee_kv.models.id_card_ocr import (
    inspect_id_card_front,
    merge_card_reads,
    parse_cccd_text,
)

SAMPLE_TEXT = """
CAN CƯỚC CONG DÂN
so: 079203042389
Họ và tên / Full name:
TRỊNH HOÀNG MINH
Ngày sinh / Date of birth: 30/12/2003
Giới tinh / Sex: Nam Quốc tich/ Nationality: Viet Nam
Quê quán / Place of origin: Dưỡng Điểm, Châu Thành, Tiền Giang
residences 14/21 Bửu Đinh
Phường 5, Quận 6, TP. Hồ Chí Minh
"""


@tagged("post_install", "-at_install")
class TestIdCardOcr(TransactionCase):
    def test_parse_printed_front(self):
        values = parse_cccd_text(SAMPLE_TEXT)
        self.assertEqual(values["identification_id"], "079203042389")
        self.assertEqual(values["name"], "TRỊNH HOÀNG MINH")
        self.assertEqual(values["birthday"], date(2003, 12, 30))
        self.assertEqual(values["gender"], "male")
        self.assertIn("Phường 5", values["emp_permanent_address"])
        self.assertIn("Quận 6", values["emp_permanent_address"])
        self.assertEqual(values["emp_place_of_origin"], "Dưỡng Điểm, Châu Thành, Tiền Giang")
        self.assertEqual(values["emp_temporary_address"], values["emp_permanent_address"])
        self.assertEqual(values["identification_by"], "Cục Cảnh Sát")
        self.assertNotIn("identification_date", values)
        self.assertNotIn("Dưỡng", values["emp_permanent_address"])

    def test_qr_keeps_its_fields_and_takes_origin_from_ocr(self):
        qr_values = {
            "identification_id": "079203042389",
            "name": "Trịnh Hoàng Minh",
            "birthday": date(2003, 12, 30),
            "gender": "male",
            "emp_permanent_address": "14/21 Bửu Đình, Phường 5, Quận 6, TP. Hồ Chí Minh",
            "identification_date": date(2023, 5, 22),
        }
        values = merge_card_reads(qr_values, SAMPLE_TEXT)
        self.assertEqual(values["emp_permanent_address"], qr_values["emp_permanent_address"])
        self.assertEqual(values["identification_date"], date(2023, 5, 22))
        self.assertEqual(values["emp_place_of_origin"], "Dưỡng Điểm, Châu Thành, Tiền Giang")
        self.assertEqual(values["emp_temporary_address"], values["emp_permanent_address"])
        self.assertEqual(values["identification_by"], "Cục Cảnh Sát")
        ocr_only = merge_card_reads({}, SAMPLE_TEXT)
        self.assertIn("14/21", ocr_only["emp_permanent_address"])
        self.assertEqual(ocr_only["emp_temporary_address"], ocr_only["emp_permanent_address"])
        self.assertEqual(ocr_only["identification_by"], "Cục Cảnh Sát")
        self.assertEqual(ocr_only["emp_place_of_origin"], "Dưỡng Điểm, Châu Thành, Tiền Giang")

    def test_parse_requires_id_and_birth_date(self):
        self.assertEqual(parse_cccd_text("Họ và tên\nNGUYEN VAN A"), {})
        self.assertEqual(parse_cccd_text("079203042389"), {})

    def test_sample_photo_reads_printed_fields(self):
        path = Path(__file__).resolve().parents[1] / "id_cards_samples" / "cccd.jpg"
        if not path.is_file():
            self.skipTest("sample card is not in the module")
        values, status = inspect_id_card_front(path.read_bytes())
        self.assertEqual(status, "ok")
        self.assertEqual(values["identification_id"], "079203042389")
        self.assertIn("MINH", values["name"])
        self.assertEqual(values["birthday"], date(2003, 12, 30))
        self.assertEqual(values["gender"], "male")
        self.assertIn("Quận 6", values["emp_permanent_address"])
