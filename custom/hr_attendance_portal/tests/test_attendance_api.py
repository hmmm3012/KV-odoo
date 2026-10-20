# -*- coding: utf-8 -*-

import base64

from odoo.tests.common import HttpCase, TransactionCase, tagged

from .common import TINY_JPEG_B64, AttendancePortalMixin


@tagged("post_install", "-at_install")
class TestAttendancePortalAPI(AttendancePortalMixin, TransactionCase):
    def test_login_success_hashes_pin_and_hides_secret(self):
        result = self._login()
        self.assertTrue(result["ok"])
        self.assertEqual(result["attendance_state"], "checked_out")
        self.assertFalse(result.get("pin"))
        self.assertFalse(result.get("token"))
        self.assertTrue(self.employee.sudo().attendance_pin_hash)
        self.assertNotEqual(self.employee.sudo().attendance_pin_hash, "1357")
        self.assertTrue(self.employee.attendance_pin_is_set)

    def test_login_failure_is_generic(self):
        missing = self._login("NO-SUCH-CODE", "1357")
        wrong_pin = self._login("KV-PORTAL-001", "0000")
        self.assertEqual(missing["error"], "invalid_credentials")
        self.assertEqual(wrong_pin["error"], "invalid_credentials")
        self.assertFalse(missing["ok"])
        self.assertFalse(wrong_pin["ok"])

    def test_check_in_out_with_gps_inside_geofence(self):
        _, token = self._issue_token()
        check_in = self._register(token, "check_in", request_id="in-1")
        self.assertTrue(check_in["ok"])
        self.assertEqual(check_in["result"], "success")
        self.assertEqual(check_in["attendance_state"], "checked_in")
        attendance = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)], limit=1)
        self.assertTrue(attendance)
        self.assertEqual(attendance.in_mode, "personal_web")
        self.assertEqual(attendance.in_location_id, self.location)
        self.assertAlmostEqual(attendance.in_latitude, 10.8231, places=4)
        self.assertTrue(attendance.in_face_image)
        self.assertTrue(attendance.in_face_detected)
        self.assertNotIn("face_image", check_in)
        self.assertNotIn("face_cosine", check_in)
        self.assertFalse(check_in.get("in_face_image"))
        self.assertFalse(check_in.get("embedding"))

        check_out = self._register(token, "check_out", request_id="out-1")
        self.assertTrue(check_out["ok"])
        self.assertEqual(check_out["attendance_state"], "checked_out")
        self.assertEqual(attendance.out_mode, "personal_web")
        self.assertTrue(attendance.out_face_image)
        self.assertTrue(attendance.out_face_detected)
        event = self.env["hr.attendance.event"].search([("request_id", "=", "in-1")])
        self.assertTrue(event.face_image)
        self.assertEqual(event.face_count, 1)
        self.assertAlmostEqual(event.face_cosine, 0.82, places=2)

    def test_resolve_location_returns_workplace_name(self):
        _, token = self._issue_token()
        result = self.portal.resolve_location(
            latitude=10.8231,
            longitude=106.6297,
            gps_accuracy=12,
            token=token,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["location_name"], "Van Phong HCM")
        self.assertFalse(result["error"])

        far = self.portal.resolve_location(
            latitude=21.0285,
            longitude=105.8542,
            gps_accuracy=12,
            token=token,
        )
        self.assertTrue(far["ok"])
        self.assertFalse(far["location_name"])
        self.assertEqual(far["error"], "unknown_location")

    def test_department_coordinates_do_not_replace_workplace(self):
        self.env["hr.department"].create({
            "name": "AEONBD",
            "company_id": self.company.id,
            "attendance_latitude": 21.0285,
            "attendance_longitude": 105.8542,
            "attendance_radius_meters": 5000,
        })
        _, token = self._issue_token()
        resolved = self.portal.resolve_location(
            latitude=10.8231,
            longitude=106.6297,
            gps_accuracy=12,
            token=token,
        )
        self.assertEqual(resolved["location_name"], "Van Phong HCM")
        self.assertFalse(resolved["error"])
        punched = self._register(token, "check_in", request_id="workplace-site")
        self.assertTrue(punched["ok"])
        self.assertEqual(punched["location_name"], "Van Phong HCM")
        event = self.env["hr.attendance.event"].search([("request_id", "=", "workplace-site")])
        self.assertEqual(event.location_id, self.location)
        self.assertEqual(event.department_id, self.department)

    def test_missing_gps_is_rejected_for_personal_web(self):
        _, token = self._issue_token()
        result = self._register(
            token,
            "check_in",
            request_id="no-gps",
            latitude=False,
            longitude=False,
            gps_accuracy=False,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "missing_gps")
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_missing_photo_is_rejected_for_personal_web(self):
        _, token = self._issue_token()
        result = self._register(
            token,
            "check_in",
            request_id="no-photo",
            face_image=False,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "missing_photo")
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_invalid_photo_is_rejected(self):
        _, token = self._issue_token()
        result = self._register(
            token,
            "check_in",
            request_id="bad-photo",
            face_image="data:text/html;base64,PGh0bWw+",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "missing_photo")
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_missing_photo_follows_company_policy(self):
        self.company.attendance_portal_missing_photo_policy = "needs_review"
        _, token = self._issue_token()
        result = self._register(
            token,
            "check_in",
            request_id="photo-review",
            face_image=False,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "needs_review")
        self.assertEqual(result["error"], "missing_photo")
        attendance = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)], limit=1)
        self.assertEqual(attendance.portal_review_status, "pending")
        self.assertFalse(attendance.in_face_image)

    def test_data_uri_jpeg_is_stored(self):
        _, token = self._issue_token()
        result = self._register(
            token,
            "check_in",
            request_id="data-uri",
            face_image="data:image/jpeg;base64," + TINY_JPEG_B64,
        )
        self.assertTrue(result["ok"])
        attendance = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)], limit=1)
        self.assertTrue(attendance.in_face_image)
        self.assertNotIn("face_image", result)

    def test_no_face_recapture_does_not_punch(self):
        self.punch_face_result = {
            "unavailable": False,
            "face_count": 0,
            "quality_reason": "no_face",
            "verify_reason": False,
            "force_reject": True,
            "cosine": None,
        }
        _, token = self._issue_token()
        result = self._register(token, "check_in", request_id="no-face")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "no_face")
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))
        event = self.env["hr.attendance.event"].search([("request_id", "=", "no-face")])
        self.assertEqual(event.result, "rejected")
        self.assertEqual(event.face_count, 0)

    def test_quality_recapture_reasons_do_not_punch(self):
        _, token = self._issue_token()
        for reason in ("face_too_small", "face_tilted", "face_turned", "multiple_faces"):
            self.punch_face_result = {
                "unavailable": False,
                "face_count": 2 if reason == "multiple_faces" else 1,
                "quality_reason": reason,
                "verify_reason": False,
                "force_reject": True,
                "cosine": None,
            }
            result = self._register(token, "check_in", request_id="quality-" + reason)
            self.assertFalse(result["ok"], reason)
            self.assertEqual(result["error"], reason)
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_face_check_unavailable_needs_review(self):
        self.punch_face_result = {
            "unavailable": True,
            "face_count": 0,
            "quality_reason": False,
            "verify_reason": "face_check_unavailable",
            "force_reject": False,
            "cosine": None,
        }
        _, token = self._issue_token()
        result = self._register(token, "check_in", request_id="face-unavailable")
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "needs_review")
        self.assertEqual(result["error"], "face_check_unavailable")
        attendance = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)], limit=1)
        self.assertTrue(attendance)
        self.assertTrue(attendance.in_face_image)
        self.assertFalse(attendance.in_face_detected)

    def test_face_not_enrolled_needs_review(self):
        self.punch_face_result = {
            "unavailable": False,
            "face_count": 1,
            "quality_reason": False,
            "verify_reason": "face_not_enrolled",
            "force_reject": False,
            "cosine": None,
        }
        _, token = self._issue_token()
        result = self._register(token, "check_in", request_id="face-not-enrolled")
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "needs_review")
        self.assertEqual(result["error"], "face_not_enrolled")
        event = self.env["hr.attendance.event"].search([("request_id", "=", "face-not-enrolled")])
        self.assertEqual(event.review_status, "pending")

    def test_face_mismatch_mid_band_needs_review(self):
        self.punch_face_result = {
            "unavailable": False,
            "face_count": 1,
            "quality_reason": False,
            "verify_reason": "face_mismatch",
            "force_reject": False,
            "cosine": 0.36,
        }
        _, token = self._issue_token()
        result = self._register(token, "check_in", request_id="face-mismatch-review")
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "needs_review")
        self.assertEqual(result["error"], "face_mismatch")
        event = self.env["hr.attendance.event"].search([("request_id", "=", "face-mismatch-review")])
        self.assertAlmostEqual(event.face_cosine, 0.36, places=2)

    def test_face_low_match_requires_recapture(self):
        self.punch_face_result = {
            "unavailable": False,
            "face_count": 1,
            "quality_reason": False,
            "verify_reason": "face_low_match",
            "force_reject": True,
            "cosine": 0.12,
        }
        _, token = self._issue_token()
        result = self._register(token, "check_in", request_id="face-low-match")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "face_low_match")
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_face_mismatch_mid_band_always_needs_review(self):
        self.company.attendance_portal_face_mismatch_policy = "reject"
        self.punch_face_result = {
            "unavailable": False,
            "face_count": 1,
            "quality_reason": False,
            "verify_reason": "face_mismatch",
            "force_reject": False,
            "cosine": 0.36,
        }
        _, token = self._issue_token()
        result = self._register(token, "check_in", request_id="face-mismatch-policy")
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "needs_review")
        self.assertEqual(result["error"], "face_mismatch")

    def test_face_preview_rejects_quality_without_punch(self):
        from unittest.mock import patch

        _, token = self._issue_token()
        with patch.object(
            type(self.portal),
            "_analyze_face_image",
            return_value={
                "unavailable": False,
                "face_count": 1,
                "quality_reason": "face_tilted",
                "embedding": None,
            },
        ):
            preview = self.portal.preview_face(face_image=TINY_JPEG_B64, token=token)
        self.assertFalse(preview["ok"])
        self.assertEqual(preview["reason"], "face_tilted")
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))
        self.assertFalse(self.env["hr.attendance.event"].search([("employee_id", "=", self.employee.id)]))

    def test_server_busy_skips_face_and_event(self):
        from unittest.mock import patch

        _, token = self._issue_token()
        with patch.object(type(self.portal), "_try_acquire_face_slot", return_value=False):
            result = self._register(token, "check_in", request_id="busy-1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "server_busy")
        self.assertEqual(result.get("retry_after"), 3)
        self.assertFalse(self.env["hr.attendance.event"].search([("request_id", "=", "busy-1")]))
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_blank_jpeg_has_no_face_when_detector_runs(self):
        from odoo.addons.hr_attendance_portal.models.face_detection import detect_face_count

        count, reason = detect_face_count(base64.b64decode(TINY_JPEG_B64))
        if reason == "face_check_unavailable":
            self.skipTest("opencv-python-headless is not installed")
        self.assertEqual(count, 0)
        self.assertEqual(reason, "no_face")

    def test_kiosk_without_photo_skips_face_check(self):
        result = self.portal.register_for_employee(
            self.employee,
            "check_in",
            latitude=10.8231,
            longitude=106.6297,
            gps_accuracy=10,
            request_id="kiosk-no-photo",
            face_image=False,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "success")
        attendance = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)], limit=1)
        self.assertFalse(attendance.in_face_image)
        self.assertFalse(attendance.in_face_detected)
        event = self.env["hr.attendance.event"].search([("request_id", "=", "kiosk-no-photo")])
        self.assertEqual(event.face_count, 0)

    def test_other_department_workplace_is_used_when_outside_home(self):
        other_location = self.env["hr.attendance.location"].create({
            "name": "Other Site",
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
        _, token = self._issue_token()
        result = self._register(
            token,
            "check_in",
            request_id="other-dept",
            latitude=21.0285,
            longitude=105.8542,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["location_name"], "Other Department")
        self.assertFalse(result["error"])
        attendance = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)], limit=1)
        self.assertEqual(attendance.in_department_id, other_department)
        self.assertEqual(attendance.in_location_id, other_location)

    def test_unknown_location_follows_company_policy(self):
        self.company.attendance_portal_no_location_policy = "needs_review"
        _, token = self._issue_token()
        result = self._register(
            token,
            "check_in",
            request_id="far-away",
            latitude=16.0,
            longitude=108.0,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "needs_review")
        self.assertEqual(result["error"], "unknown_location")
        self.assertFalse(result["location_name"])
        attendance = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)], limit=1)
        self.assertEqual(attendance.portal_review_status, "pending")

        event = self.env["hr.attendance.event"].search([("request_id", "=", "far-away")])
        event.action_mark_reviewed()
        self.assertEqual(event.review_status, "reviewed")
        self.assertEqual(attendance.portal_review_status, "reviewed")

    def test_expired_or_revoked_session_is_rejected(self):
        session, token = self._issue_token()
        session._revoke()
        result = self._register(token, "check_in", request_id="revoked")
        self.assertEqual(result["error"], "invalid_session")

    def test_inactive_employee_cannot_check_in(self):
        _, token = self._issue_token()
        self.employee.active = False
        result = self._register(token, "check_in", request_id="inactive")
        self.assertIn(result["error"], ("inactive_employee", "invalid_session"))
        self.assertFalse(result["ok"])
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_kiosk_helper_uses_same_logic_and_revokes_session(self):
        result = self.portal.register_for_employee(
            self.employee,
            "check_in",
            latitude=10.8231,
            longitude=106.6297,
            gps_accuracy=10,
            request_id="kiosk-1",
        )
        self.assertTrue(result["ok"])
        sessions = self.env["hr.attendance.session"].search([
            ("employee_id", "=", self.employee.id),
            ("source", "=", "kiosk"),
            ("revoked_at", "=", False),
        ])
        self.assertFalse(sessions)


@tagged("post_install", "-at_install")
class TestAttendancePortalHttp(AttendancePortalMixin, HttpCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({
            "name": "HTTP Portal Employee",
            "emp_code": "KV-HTTP-001",
            "pin": "2468",
            "attendance_portal_enabled": True,
        })
        location = self.env["hr.attendance.location"].create({
            "name": "HTTP Workplace",
            "latitude": 10.8231,
            "longitude": 106.6297,
            "allowed_radius_meters": 250,
            "company_id": self.env.company.id,
        })
        department = self.env["hr.department"].create({
            "name": "HTTP Department",
            "company_id": self.env.company.id,
            "attendance_location_id": location.id,
        })
        self.employee.department_id = department

    def test_portal_page_is_public(self):
        response = self.url_open("/attendance")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Chấm công", response.text)
        self.assertIn("attendance_portal.js?v=20261019l", response.text)

    def test_http_login_sets_cookie_and_check_in(self):
        result = self.make_jsonrpc_request("/attendance/api/login", {
            "employee_code": "KV-HTTP-001",
            "pin": "2468",
            "source": "personal_web",
        })
        self.assertTrue(result["ok"])
        self.assertIn("attendance_portal_session", self.opener.cookies)
        punched = self.make_jsonrpc_request("/attendance/api/check", {
            "event_type": "check_in",
            "latitude": 10.8231,
            "longitude": 106.6297,
            "gps_accuracy": 15,
            "face_image": TINY_JPEG_B64,
            "request_id": "http-in-1",
            "source": "personal_web",
        })
        self.assertTrue(punched["ok"])
        self.assertEqual(punched["attendance_state"], "checked_in")

    def test_http_check_in_without_preview(self):
        result = self.make_jsonrpc_request("/attendance/api/login", {
            "employee_code": "KV-HTTP-001",
            "pin": "2468",
            "source": "personal_web",
        })
        self.assertTrue(result["ok"])
        punched = self.make_jsonrpc_request("/attendance/api/check", {
            "event_type": "check_in",
            "latitude": 10.8231,
            "longitude": 106.6297,
            "gps_accuracy": 15,
            "face_image": TINY_JPEG_B64,
            "request_id": "http-in-no-preview",
            "source": "personal_web",
        })
        self.assertTrue(punched["ok"])
        self.assertEqual(punched["attendance_state"], "checked_in")

    def test_http_face_preview_does_not_punch(self):
        from unittest.mock import patch

        login = self.make_jsonrpc_request("/attendance/api/login", {
            "employee_code": "KV-HTTP-001",
            "pin": "2468",
            "source": "personal_web",
        })
        self.assertTrue(login["ok"])
        with patch.object(
            type(self.env["hr.attendance.portal"]),
            "_analyze_face_image",
            return_value={
                "unavailable": False,
                "face_count": 1,
                "quality_reason": "face_too_small",
                "embedding": None,
            },
        ):
            preview = self.make_jsonrpc_request("/attendance/api/face_preview", {
                "face_image": TINY_JPEG_B64,
            })
        self.assertFalse(preview["ok"])
        self.assertEqual(preview["reason"], "face_too_small")
        self.assertNotIn("embedding", preview)
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))


@tagged("post_install", "-at_install")
class TestFacePunchProcess(TransactionCase):
    def test_one_to_one_match_and_not_enrolled(self):
        from unittest.mock import patch

        from odoo.addons.hr_attendance_portal.models.face_pipeline import packing_embedding

        portal = self.env["hr.attendance.portal"]
        employee = self.env["hr.employee"].create({
            "name": "Face Process Employee",
            "emp_code": "KV-FACE-001",
            "pin": "1357",
        })
        vec = [1.0] + [0.0] * 127
        analyzed = {
            "unavailable": False,
            "face_count": 1,
            "quality_reason": False,
            "embedding": vec,
        }
        with patch.object(type(portal), "_analyze_face_image", return_value=analyzed):
            missing = portal._process_punch_face(b"jpeg", employee)
            self.assertEqual(missing["verify_reason"], "face_not_enrolled")
            employee.sudo().with_context(skip_attendance_face_embed=True).write({
                "attendance_face_embedding": packing_embedding(vec),
            })
            matched = portal._process_punch_face(b"jpeg", employee)
            self.assertFalse(matched["verify_reason"])
            self.assertFalse(matched["force_reject"])
            self.assertGreaterEqual(matched["cosine"], 0.45)
