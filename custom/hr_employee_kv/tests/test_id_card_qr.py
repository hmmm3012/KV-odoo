# -*- coding: utf-8 -*-

from datetime import date
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.hr_employee_kv.models.id_card_qr import (
    decode_id_card_front,
    parse_cccd_payload,
)

SAMPLE = (
    "001234567890|123456789|NGUYEN VAN A|01011990|Nam|"
    "So 1 Duong ABC, Phuong 1, Quan 1, TP Ho Chi Minh|15082021"
)
PARSED = {
    "identification_id": "001234567890",
    "name": "NGUYEN VAN A",
    "birthday": date(1990, 1, 1),
    "gender": "male",
    "emp_permanent_address": "So 1 Duong ABC, Phuong 1, Quan 1, TP Ho Chi Minh",
    "identification_date": date(2021, 8, 15),
}


@tagged("post_install", "-at_install")
class TestIdCardQr(TransactionCase):
    def test_parse_standard_payload(self):
        self.assertEqual(parse_cccd_payload(SAMPLE), PARSED)

    def test_parse_empty_old_id_and_female(self):
        payload = "079203001234||TRAN THI B|31121999|Nữ|Xa A, Huyen B, Tinh C|01012024|extra"
        values = parse_cccd_payload(payload)
        self.assertEqual(values["identification_id"], "079203001234")
        self.assertEqual(values["name"], "TRAN THI B")
        self.assertEqual(values["gender"], "female")
        self.assertEqual(values["birthday"], date(1999, 12, 31))
        self.assertEqual(values["identification_date"], date(2024, 1, 1))
        self.assertEqual(values["emp_permanent_address"], "Xa A, Huyen B, Tinh C")

    def test_parse_nine_digit_id_and_nu_without_accent(self):
        values = parse_cccd_payload("123456789||LE VAN C|02021988|Nu|Dia chi|03032020")
        self.assertEqual(values["identification_id"], "123456789")
        self.assertEqual(values["gender"], "female")

    def test_decode_finds_qr_in_upper_right_of_large_photo(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV is not installed")
        encoder = cv2.QRCodeEncoder_create()
        qr = encoder.encode(SAMPLE)
        small = cv2.resize(qr, (160, 160), interpolation=cv2.INTER_NEAREST)
        if small.ndim == 2:
            small = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
        canvas = np.full((1400, 2000, 3), 240, np.uint8)
        canvas[30:190, 1780:1940] = small
        ok, encoded = cv2.imencode(".jpg", canvas)
        self.assertTrue(ok)
        values = decode_id_card_front(encoded.tobytes())
        self.assertEqual(values["identification_id"], "001234567890")
        self.assertEqual(values["name"], "NGUYEN VAN A")

    def test_parse_rejects_unreadable_payloads(self):
        self.assertEqual(parse_cccd_payload(""), {})
        self.assertEqual(parse_cccd_payload("not a qr code"), {})
        self.assertEqual(parse_cccd_payload("ABC|1|NAME|01011990|Nam|Addr|01012021"), {})
        self.assertEqual(parse_cccd_payload("001234567890|1|NAME|32011990|Nam|Addr|01012021"), {})
        self.assertNotIn("identification_by", parse_cccd_payload(SAMPLE))

    def test_create_does_not_autofill_from_id_card(self):
        front = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        with patch(
            "odoo.addons.hr_employee_kv.models.id_card_ocr.inspect_id_card",
            return_value=(dict(PARSED), "qr"),
        ):
            employee = self.env["hr.employee"].create({
                "name": "Manual Name",
                "id_card_front": front,
                "id_card_back": front,
                "emp_code": "QR-KEEP-001",
                "company_id": self.env.company.id,
            })
        self.assertEqual(employee.name, "Manual Name")
        self.assertFalse(employee.identification_id)
        self.assertFalse(employee.birthday)
        self.assertFalse(employee.sex)
        self.assertTrue(employee.id_card_front)
        self.assertTrue(employee.id_card_back)

    def test_read_id_card_from_images_returns_mapped_fields(self):
        front = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        with patch(
            "odoo.addons.hr_employee_kv.models.models.inspect_id_card",
            return_value=(dict(PARSED), "qr"),
        ):
            result = self.env["hr.employee"].read_id_card_from_images(front=front)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "qr")
        self.assertEqual(result["values"]["name"], "NGUYEN VAN A")
        self.assertEqual(result["values"]["identification_id"], "001234567890")
        self.assertEqual(result["values"]["birthday"], "1990-01-01")
        self.assertEqual(result["values"]["sex"], "male")
        self.assertEqual(result["values"]["identification_date"], "2021-08-15")
        self.assertIn("mã QR", result["message"])

    def test_read_id_card_from_images_without_photo(self):
        result = self.env["hr.employee"].read_id_card_from_images()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["notification_type"], "warning")
        self.assertIn("Chưa có ảnh CCCD", result["message"])

    def test_action_fill_from_id_card_writes_fields(self):
        from odoo.exceptions import UserError

        front = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        empty = self.env["hr.employee"].create({
            "name": "No Card",
            "emp_code": "QR-EMPTY-001",
            "company_id": self.env.company.id,
        })
        with self.assertRaises(UserError) as error:
            empty.action_fill_from_id_card()
        self.assertIn("Chưa có ảnh CCCD", error.exception.args[0])

        employee = self.env["hr.employee"].create({
            "name": "Manual Name",
            "id_card_front": front,
            "emp_code": "QR-FILL-001",
            "company_id": self.env.company.id,
        })
        with patch(
            "odoo.addons.hr_employee_kv.models.models.inspect_id_card",
            return_value=(dict(PARSED), "qr"),
        ):
            action = employee.action_fill_from_id_card()
        self.assertEqual(employee.name, "NGUYEN VAN A")
        self.assertEqual(employee.identification_id, "001234567890")
        self.assertEqual(employee.birthday, date(1990, 1, 1))
        self.assertEqual(employee.sex, "male")
        self.assertEqual(employee.emp_permanent_address, PARSED["emp_permanent_address"])
        self.assertEqual(employee.identification_date, date(2021, 8, 15))
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "success")
        self.assertIn("mã QR", action["params"]["message"])
