# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, tagged

from .common import AttendancePortalMixin


@tagged("post_install", "-at_install")
class TestAttendancePortalConcurrency(AttendancePortalMixin, TransactionCase):
    def test_duplicate_request_id_returns_original_result(self):
        _, token = self._issue_token()
        first = self._register(token, "check_in", request_id="same-req")
        second = self._register(token, "check_in", request_id="same-req")
        self.assertTrue(first["ok"])
        self.assertEqual(first["result"], second["result"])
        self.assertEqual(first["attendance_state"], second["attendance_state"])
        attendances = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)])
        self.assertEqual(len(attendances), 1)
        events = self.env["hr.attendance.event"].search([("request_id", "=", "same-req")])
        self.assertEqual(len(events), 1)

    def test_second_check_in_is_rejected_without_creating_overlap(self):
        _, token = self._issue_token()
        first = self._register(token, "check_in", request_id="first-in")
        second = self._register(token, "check_in", request_id="second-in")
        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(second["error"], "already_checked_in")
        self.assertEqual(
            self.env["hr.attendance"].search_count([("employee_id", "=", self.employee.id)]),
            1,
        )

    def test_check_out_without_check_in_is_rejected(self):
        _, token = self._issue_token()
        result = self._register(token, "check_out", request_id="orphan-out")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "not_checked_in")

    def test_request_id_from_another_employee_is_not_reused(self):
        other = self.env["hr.employee"].create({
            "name": "Concurrent Other",
            "emp_code": "KV-PORTAL-009",
            "pin": "9876",
        })
        _, token_a = self._issue_token(self.employee)
        _, token_b = self._issue_token(other)
        first = self._register(token_a, "check_in", request_id="shared-id")
        stolen = self.portal.register(
            "check_in",
            latitude=10.8231,
            longitude=106.6297,
            gps_accuracy=10,
            request_id="shared-id",
            token=token_b,
        )
        self.assertTrue(first["ok"])
        self.assertEqual(stolen["error"], "duplicate_request")
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", other.id)]))
