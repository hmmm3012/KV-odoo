# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from .common import TINY_JPEG_B64, AttendancePortalMixin


@tagged("post_install", "-at_install")
class TestAttendancePortalSecurity(AttendancePortalMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public_user = cls.env.ref("base.public_user")
        cls.internal_user = new_test_user(
            cls.env,
            login="portal_att_user",
            groups="base.group_user",
        )
        cls.officer = new_test_user(
            cls.env,
            login="portal_att_officer",
            groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
        )

    def test_public_user_cannot_create_attendance(self):
        with self.assertRaises(AccessError):
            self.env["hr.attendance"].with_user(self.public_user).create({
                "employee_id": self.employee.id,
            })

    def test_public_user_cannot_read_pin_or_hash(self):
        employee = self.employee.with_user(self.public_user)
        with self.assertRaises(AccessError):
            employee.read(["pin"])
        with self.assertRaises(AccessError):
            employee.read(["attendance_pin_hash"])

    def test_public_user_cannot_read_sessions_or_events(self):
        self._login()
        with self.assertRaises(AccessError):
            self.env["hr.attendance.session"].with_user(self.public_user).search([])
        with self.assertRaises(AccessError):
            self.env["hr.attendance.event"].with_user(self.public_user).search([])

    def test_internal_user_cannot_use_portal_models_without_attendance_group(self):
        with self.assertRaises(AccessError):
            self.env["hr.attendance.location"].with_user(self.internal_user).create({
                "name": "Forbidden",
                "latitude": 1,
                "longitude": 1,
            })

    def test_session_cannot_punch_for_another_employee(self):
        other = self.env["hr.employee"].create({
            "name": "Other Employee",
            "emp_code": "KV-PORTAL-002",
            "pin": "2468",
        })
        _, token = self._issue_token(self.employee)
        result = self.portal.register(
            "check_in",
            latitude=10.8231,
            longitude=106.6297,
            gps_accuracy=10,
            face_image=TINY_JPEG_B64,
            request_id="cross-employee",
            token=token,
        )
        self.assertTrue(result["ok"])
        attendance = self.env["hr.attendance"].search([("employee_id", "=", other.id)])
        self.assertFalse(attendance)
        own = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)])
        self.assertTrue(own)

    def test_failed_login_does_not_log_pin(self):
        self._login("KV-PORTAL-001", "0000")
        event = self.env["hr.attendance.event"].search([
            ("employee_id", "=", self.employee.id),
            ("failure_reason_code", "=", "invalid_credentials"),
        ], limit=1)
        self.assertTrue(event)
        self.assertNotIn("0000", str(event.read()[0]))
        self.assertNotIn("1357", (event.review_note or ""))

    def test_rate_limit_lockout_is_temporary(self):
        self.company.attendance_portal_pin_max_attempts = 3
        self.company.attendance_portal_pin_window_minutes = 15
        for _ in range(3):
            result = self._login("KV-PORTAL-001", "0000")
            self.assertEqual(result["error"], "invalid_credentials")
        locked = self._login("KV-PORTAL-001", "0000")
        self.assertEqual(locked["error"], "too_many_attempts")
        self.assertTrue(locked.get("retry_after"))
        success_after_lock = self._login("KV-PORTAL-001", "1357")
        self.assertEqual(success_after_lock["error"], "too_many_attempts")

    def test_officer_cannot_read_face_embedding(self):
        fake_vec = [0.1] * 128
        with patch(
            "odoo.addons.hr_attendance_portal.models.face_pipeline.process_face",
            return_value={
                "unavailable": False,
                "face_count": 1,
                "quality_reason": False,
                "embedding": fake_vec,
            },
        ):
            self.employee.write({"attendance_face_image": TINY_JPEG_B64})
        self.assertTrue(self.employee.attendance_face_is_enrolled)
        self.assertTrue(self.employee.sudo().attendance_face_embedding)
        for user in (self.officer, self.internal_user):
            employee = self.employee.with_user(user)
            try:
                data = employee.read(["attendance_face_embedding"])
            except AccessError:
                continue
            self.assertFalse(data[0].get("attendance_face_embedding"))

    def test_site_captain_reads_only_their_department(self):
        captain = new_test_user(
            self.env,
            login="portal_site_captain",
            groups="hr_attendance_portal.group_hr_attendance_site_captain",
        )
        other_location = self.env["hr.attendance.location"].create({
            "name": "Other Parking",
            "latitude": 21.0285,
            "longitude": 105.8542,
            "allowed_radius_meters": 250,
            "company_id": self.company.id,
        })
        other_department = self.env["hr.department"].create({
            "name": "Other Department",
            "company_id": self.company.id,
            "attendance_location_id": other_location.id,
        })
        other = self.env["hr.employee"].create({
            "name": "Other Site Employee",
            "emp_code": "KV-PORTAL-008",
            "pin": "2468",
            "attendance_portal_enabled": True,
            "company_id": self.company.id,
            "department_id": other_department.id,
        })
        stranger = self.env["hr.employee"].create({
            "name": "Unassigned Employee",
            "emp_code": "KV-PORTAL-007",
            "pin": "1111",
            "attendance_portal_enabled": True,
            "company_id": self.company.id,
        })
        captain.hr_authorized_department_ids = self.department
        _, token = self._issue_token()
        self._register(token, "check_in", request_id="captain-in")
        _, other_token = self._issue_token(other)
        self._register(
            other_token,
            "check_in",
            request_id="other-in",
            latitude=21.0285,
            longitude=105.8542,
        )

        visitor = self.env["hr.employee"].create({
            "name": "Visitor Employee",
            "emp_code": "KV-PORTAL-010",
            "pin": "2222",
            "attendance_portal_enabled": True,
            "company_id": self.company.id,
            "department_id": other_department.id,
        })
        _, visitor_token = self._issue_token(visitor)
        self._register(visitor_token, "check_in", request_id="visitor-in")

        visible = self.env["hr.attendance"].with_user(captain).search([])
        self.assertEqual(set(visible.mapped("employee_id").ids), {self.employee.id, visitor.id})
        self.assertEqual(visitor.with_user(captain).name, "Visitor Employee")
        with self.assertRaises(AccessError):
            visible.write({"in_gps_accuracy": 99})

        employees = self.env["hr.employee"].with_user(captain)
        self.assertIn(self.employee, employees.search([]))
        self.assertNotIn(stranger, employees.search([]))
        self.assertNotIn(other, employees.search([]))
        with self.assertRaises(AccessError):
            self.employee.with_user(captain).write({"name": "Changed"})
        with self.assertRaises(AccessError):
            self.employee.with_user(captain).read(["pin"])

        staff = employees.search([("department_id", "in", captain._hr_site_captain_department_ids())])
        self.assertIn(self.employee, staff)
        self.assertNotIn(visitor, staff)
        self.assertIn(visitor, employees.search([]))
        with self.assertRaises(AccessError):
            visitor.with_user(captain).get_formview_action()

        events = self.env["hr.attendance.event"].with_user(captain).search([])
        self.assertEqual(set(events.mapped("request_id")), {"captain-in", "visitor-in"})
        with self.assertRaises(AccessError):
            events.write({"review_note": "Captain edit"})

        self.env["hr.attendance"].sudo().create({
            "employee_id": stranger.id,
            "check_in": "2026-10-19 01:00:00",
            "in_location_id": self.location.id,
        })
        self.assertEqual(stranger.with_user(captain).name, "Unassigned Employee")
        self.assertIn(
            stranger,
            self.env["hr.attendance"].with_user(captain).search([]).employee_id,
        )

    def test_officer_can_review_events(self):
        self.employee.attendance_manager_id = self.officer.id
        _, token = self._issue_token()
        self.company.attendance_portal_no_location_policy = "needs_review"
        self._register(token, request_id="review-1", latitude=16.0, longitude=108.0)
        event = self.env["hr.attendance.event"].search([("request_id", "=", "review-1")])
        event.with_user(self.officer).write({"review_note": "Checked by HR"})
        event.with_user(self.officer).action_mark_reviewed()
        self.assertEqual(event.review_status, "reviewed")

    def _fake_face_embedding(self):
        return patch(
            "odoo.addons.hr_attendance_portal.models.face_pipeline.process_face",
            return_value={
                "unavailable": False,
                "face_count": 1,
                "quality_reason": False,
                "embedding": [0.2] * 128,
            },
        )

    def test_aeon_employee_uses_photo_and_code_pin(self):
        department = self.env["hr.department"].create({
            "name": "AEONHD",
            "company_id": self.company.id,
        })
        child = self.env["hr.department"].create({
            "name": "AEONHD Shift A",
            "parent_id": department.id,
            "company_id": self.company.id,
        })
        with self._fake_face_embedding():
            employee = self.env["hr.employee"].create({
                "name": "Aeon HD Staff",
                "emp_code": "AEONHD0012345",
                "department_id": department.id,
                "image_1920": TINY_JPEG_B64,
                "company_id": self.company.id,
            })
            later = self.env["hr.employee"].create({
                "name": "Aeon HL Staff",
                "emp_code": "HL12",
                "company_id": self.company.id,
            })
            hl = self.env["hr.department"].create({
                "name": "aeonhl",
                "company_id": self.company.id,
            })
            later.write({
                "department_id": hl.id,
                "image_1920": TINY_JPEG_B64,
            })
            child_employee = self.env["hr.employee"].create({
                "name": "Aeon Child",
                "emp_code": "KV998877",
                "department_id": child.id,
                "company_id": self.company.id,
            })
        self.assertEqual(employee.pin, "12345")
        self.assertTrue(employee.attendance_pin_is_set)
        self.assertTrue(employee.sudo().attendance_pin_hash)
        self.assertNotEqual(employee.sudo().attendance_pin_hash, "12345")
        self.assertTrue(employee.attendance_face_image)
        self.assertTrue(employee.attendance_face_is_enrolled)
        self.assertEqual(later.pin, "00012")
        self.assertTrue(later.attendance_face_is_enrolled)
        self.assertEqual(child_employee.pin, "98877")
        kept = self.env["hr.employee"].create({
            "name": "Custom Pin",
            "emp_code": "AEONHD0099999",
            "pin": "1357",
            "department_id": department.id,
            "company_id": self.company.id,
        })
        self.assertEqual(kept.pin, "1357")

    def test_new_employee_uses_photo_and_code_pin(self):
        with self._fake_face_embedding():
            employee = self.env["hr.employee"].create({
                "name": "Other Site",
                "emp_code": "KV0012345",
                "department_id": self.department.id,
                "image_1920": TINY_JPEG_B64,
                "company_id": self.company.id,
            })
        self.assertEqual(employee.pin, "12345")
        self.assertTrue(employee.attendance_face_image)
        self.assertTrue(employee.attendance_face_is_enrolled)

    def test_aeon_bad_photo_still_saves_employee(self):
        department = self.env["hr.department"].create({
            "name": "AEONHL",
            "company_id": self.company.id,
        })
        with patch(
            "odoo.addons.hr_attendance_portal.models.face_pipeline.process_face",
            return_value={
                "unavailable": False,
                "face_count": 0,
                "quality_reason": "no_face",
                "embedding": False,
            },
        ):
            employee = self.env["hr.employee"].create({
                "name": "No Face",
                "emp_code": "AEONHL0004321",
                "department_id": department.id,
                "image_1920": TINY_JPEG_B64,
                "company_id": self.company.id,
            })
        self.assertTrue(employee.exists())
        self.assertEqual(employee.pin, "04321")
        self.assertTrue(employee.attendance_face_image)
        self.assertFalse(employee.attendance_face_is_enrolled)
