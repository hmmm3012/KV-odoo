# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

from .common import AttendancePortalMixin


@tagged("post_install", "-at_install")
class TestAttendanceSession(AttendancePortalMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.attendance_standard_hours = 8.0
        cls.company.attendance_overtime_cap_hours = 4.0
        cls.company.attendance_missing_checkout_hours = 12.0
        cls.captain = new_test_user(
            cls.env,
            login="session_captain",
            groups="hr_attendance_portal.group_hr_attendance_site_captain",
        )
        cls.captain.hr_authorized_department_ids = cls.department
        cls.officer = new_test_user(
            cls.env,
            login="session_officer",
            groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user",
        )
        cls.employee.attendance_manager_id = cls.officer

    def _session(self, hours, check_out=True):
        end = fields.Datetime.now()
        start = end - timedelta(hours=hours)
        attendance = self.env["hr.attendance"].create({
            "employee_id": self.employee.id,
            "check_in": start,
        })
        if check_out:
            attendance.with_context(attendance_original_punch=True).write({"check_out": end})
        return attendance

    def test_worked_time_rounds_to_half_hour(self):
        Attendance = self.env["hr.attendance"]
        end = fields.Datetime.now().replace(microsecond=0)
        cases = (
            (timedelta(hours=12, minutes=44), 12.5),
            (timedelta(hours=12, minutes=45), 13.0),
            (timedelta(hours=12, minutes=14), 12.0),
            (timedelta(hours=12, minutes=15), 12.5),
            (timedelta(hours=12), 12.0),
            (timedelta(hours=12, minutes=30), 12.5),
        )
        for delta, expected in cases:
            rounded = Attendance._round_elapsed_hours(end - delta, end)
            self.assertAlmostEqual(rounded, expected, places=4, msg=str(delta))
            self.assertAlmostEqual(
                Attendance._round_worked_hours(delta.total_seconds() / 3600.0),
                expected,
                places=4,
                msg=str(delta),
            )

        under = self._session(7 + 44 / 60)
        self.assertAlmostEqual(under.raw_elapsed_hours, 7 + 44 / 60, places=2)
        self.assertAlmostEqual(under.recognized_regular_hours, 7.5, places=4)
        self.assertAlmostEqual(under.payroll_regular_hours, 7.5, places=4)
        self.assertEqual(under.overtime_candidate_hours, 0)

        over_end = under.check_in - timedelta(minutes=1)
        over = self.env["hr.attendance"].create({
            "employee_id": self.employee.id,
            "check_in": over_end - timedelta(hours=8, minutes=15),
        })
        over.with_context(attendance_original_punch=True).write({"check_out": over_end})
        self.assertEqual(over.session_state, "pending_review")
        self.assertAlmostEqual(over.recognized_regular_hours, 8, places=4)
        self.assertAlmostEqual(over.overtime_candidate_hours, 0.5, places=4)

    def test_shift_under_fifteen_minutes_is_saved_off_valid_list(self):
        short = self._session(14 / 60.0)
        self.assertTrue(short.check_in and short.check_out)
        self.assertEqual(short.recognized_regular_hours, 0)
        self.assertEqual(short.payroll_regular_hours, 0)
        action = self.env.ref("hr_attendance_portal.action_site_captain_attendance")
        domain = safe_eval(action.domain)
        self.assertFalse(self.env["hr.attendance"].search([("id", "=", short.id)] + domain))

        end = short.check_in - timedelta(minutes=1)
        counted = self.env["hr.attendance"].create({
            "employee_id": self.employee.id,
            "check_in": end - timedelta(minutes=15),
        })
        counted.with_context(attendance_original_punch=True).write({"check_out": end})
        self.assertAlmostEqual(counted.recognized_regular_hours, 0.5, places=4)
        self.assertTrue(self.env["hr.attendance"].search([("id", "=", counted.id)] + domain))

    def test_short_session_is_validated(self):
        attendance = self._session(6)
        self.assertEqual(attendance.session_state, "validated")
        self.assertAlmostEqual(attendance.recognized_regular_hours, 6, places=2)
        self.assertEqual(attendance.payroll_overtime_hours, 0)
        self.assertEqual(attendance.overtime_state, "not_required")

    def test_long_session_waits_for_captain_and_hr(self):
        attendance = self._session(15)
        self.assertEqual(attendance.session_state, "pending_review")
        self.assertEqual(attendance.exception_code, "excessive_duration")
        self.assertAlmostEqual(attendance.recognized_regular_hours, 8, places=2)
        self.assertAlmostEqual(attendance.overtime_candidate_hours, 7, places=2)
        self.assertEqual(attendance.payroll_overtime_hours, 0)
        self.assertEqual(attendance.overtime_state, "pending_captain")

    def test_captain_cannot_increase_hours_or_overtime(self):
        attendance = self._session(15)
        captain_attendance = attendance.with_user(self.captain)
        with self.assertRaises(UserError):
            captain_attendance.action_reduce_regular(9, "too much")
        with self.assertRaises(UserError):
            captain_attendance.action_captain_overtime(5, "above cap")
        captain_attendance.action_reduce_regular(6, "left early")
        self.assertAlmostEqual(attendance.recognized_regular_hours, 6, places=2)
        self.assertAlmostEqual(attendance.payroll_regular_hours, 6, places=2)
        self.assertTrue(attendance.hour_decision_ids)
        captain_attendance.action_captain_overtime(3, "worked late")
        self.assertEqual(attendance.payroll_overtime_hours, 0)
        self.assertEqual(attendance.overtime_state, "pending_hr_review")
        self.assertEqual(attendance.overtime_case_ids.captain_user_id, self.captain)

    def test_captain_decides_several_overtime_shifts_at_once(self):
        now = fields.Datetime.now()

        def shift(hours, end):
            attendance = self.env["hr.attendance"].create({
                "employee_id": self.employee.id,
                "check_in": end - timedelta(hours=hours),
            })
            attendance.with_context(attendance_original_punch=True).write({"check_out": end})
            return attendance

        first = shift(15, now - timedelta(days=4))
        second = shift(14, now - timedelta(days=3))
        short = shift(6, now - timedelta(days=2))
        selected = (first | second | short).with_user(self.captain)
        with self.assertRaises(UserError):
            short.with_user(self.captain).action_open_bulk_overtime_wizard()
        action = selected.action_open_bulk_overtime_wizard()
        wizard = self.env["hr.attendance.overtime.bulk.wizard"].with_user(self.captain).with_context(
            **action["context"]
        ).create({"reason": "approved together"})
        self.assertEqual(wizard.shift_count, 2)
        self.assertFalse(wizard.rejected)
        wizard.action_apply()
        self.assertEqual(first.overtime_state, "pending_hr_review")
        self.assertEqual(second.overtime_state, "pending_hr_review")
        self.assertAlmostEqual(first.overtime_case_ids.captain_hours, 4, places=2)
        self.assertAlmostEqual(second.overtime_case_ids.captain_hours, 4, places=2)
        self.assertEqual(first.payroll_overtime_hours, 0)
        self.assertEqual(short.overtime_state, "not_required")

        rejected_first = shift(15, now - timedelta(days=1))
        rejected_second = shift(13, now - timedelta(hours=1))
        reject_action = (rejected_first | rejected_second).with_user(self.captain).with_context(
            overtime_bulk_reject=True
        ).action_open_bulk_overtime_wizard()
        reject_wizard = self.env["hr.attendance.overtime.bulk.wizard"].with_user(self.captain).with_context(
            **reject_action["context"]
        ).create({"reason": "no overtime"})
        self.assertTrue(reject_wizard.rejected)
        reject_wizard.action_apply()
        self.assertEqual(rejected_first.overtime_case_ids.captain_hours, 0)
        self.assertEqual(rejected_second.overtime_case_ids.captain_hours, 0)
        self.assertEqual(rejected_first.overtime_state, "pending_hr_review")

    def test_hr_cannot_exceed_captain_overtime(self):
        attendance = self._session(15)
        attendance.with_user(self.captain).action_captain_overtime(2, "two hours")
        with self.assertRaises(UserError):
            attendance.with_user(self.officer).action_hr_overtime(3, "too much")
        attendance.with_user(self.officer).action_hr_overtime(2, "matches captain")
        self.assertEqual(attendance.payroll_overtime_hours, 2)
        self.assertEqual(attendance.overtime_state, "hr_reviewed")
        self.assertEqual(attendance.check_in, attendance.check_in)

    def test_deny_keeps_original_times_and_events(self):
        attendance = self._session(15)
        original_in = attendance.check_in
        original_out = attendance.check_out
        event = self.env["hr.attendance.event"].sudo().create({
            "employee_id": self.employee.id,
            "attendance_id": attendance.id,
            "event_type": "check_in",
            "result": "success",
            "source": "personal_web",
            "request_id": "session-deny-event",
        })
        attendance.with_user(self.captain).action_deny_session("mistaken punch")
        self.assertEqual(attendance.session_state, "denied")
        self.assertEqual(attendance.recognized_regular_hours, 0)
        self.assertEqual(attendance.payroll_regular_hours, 0)
        self.assertEqual(attendance.payroll_overtime_hours, 0)
        self.assertEqual(attendance.check_in, original_in)
        self.assertEqual(attendance.check_out, original_out)
        self.assertTrue(event.exists())
        with self.assertRaises(UserError):
            event.with_user(self.officer).unlink()

    def test_correction_does_not_overwrite_checkout(self):
        attendance = self._session(15)
        original_out = attendance.check_out
        proposed = attendance.check_in + timedelta(hours=8)
        own = attendance.with_user(self.officer).action_request_correction(
            "check_in", attendance.check_in, "officer cannot self-approve"
        )
        with self.assertRaises(UserError):
            own.with_user(self.officer).action_approve("self approval")
        correction = attendance.with_user(self.captain).action_request_correction(
            "check_out", proposed, "forgot the real checkout"
        )
        self.assertEqual(correction.requester_id, self.captain)
        self.assertEqual(attendance.session_state, "modification_pending")
        self.assertEqual(attendance.check_out, original_out)
        with self.assertRaises(AccessError):
            correction.with_user(self.captain).action_approve("self approval")
        correction.with_user(self.officer).write({"decision_reason": "accepted"})
        correction.with_user(self.officer).action_approve_button()
        self.assertEqual(attendance.check_out, original_out)
        self.assertEqual(attendance.effective_check_out, proposed)
        self.assertAlmostEqual(attendance.recognized_regular_hours, 8, places=2)
        self.assertEqual(attendance.payroll_overtime_hours, 0)

    def test_closed_session_rejects_decisions(self):
        attendance = self._session(6)
        attendance.with_user(self.officer).action_close_session()
        with self.assertRaises(UserError):
            attendance.with_user(self.captain).action_reduce_regular(4, "too late")

    def test_original_timestamps_cannot_be_edited(self):
        attendance = self._session(6)
        with self.assertRaises(UserError):
            attendance.with_user(self.officer).write({
                "check_out": fields.Datetime.now(),
            })

    def test_captain_confirms_missing_checkout(self):
        attendance = self._session(13, check_out=False)
        checkout = attendance.check_in + timedelta(hours=9)
        attendance.with_user(self.captain).action_confirm_checkout(checkout, "left at the end of the shift")
        self.assertEqual(attendance.check_out, checkout)
        self.assertEqual(attendance.out_mode, "manual")
        self.assertEqual(attendance.employee_id.attendance_state, "checked_out")
        self.assertAlmostEqual(attendance.recognized_regular_hours, 8, places=4)
        self.assertAlmostEqual(attendance.overtime_candidate_hours, 1, places=4)
        decision = attendance.hour_decision_ids.filtered(lambda item: item.decision_type == "confirm_checkout")
        self.assertEqual(decision.user_id, self.captain)
        with self.assertRaises(UserError):
            attendance.with_user(self.captain).action_confirm_checkout(checkout, "again")
        with self.assertRaises(UserError):
            self._session(1, check_out=False).with_user(self.captain).action_confirm_checkout(
                fields.Datetime.now() + timedelta(hours=1), "future"
            )

    def test_missing_checkout_is_flagged_without_inventing_time(self):
        attendance = self._session(13, check_out=False)
        self.assertFalse(attendance.check_out)
        self.assertEqual(attendance.exception_code, "missing_checkout")
        self.assertEqual(attendance.session_state, "pending_review")
        self.assertEqual(attendance.recognized_regular_hours, 0)

    def test_hr_can_restore_denied_session_without_deleting_history(self):
        attendance = self._session(6)
        attendance.with_user(self.captain).action_deny_session("wrong person")
        with self.assertRaises(AccessError):
            attendance.with_user(self.captain).action_restore_session(6, "captain cannot restore")
        attendance.with_user(self.officer).action_restore_session(5, "confirmed part of the shift")
        self.assertEqual(len(attendance.hour_decision_ids), 2)
        self.assertAlmostEqual(attendance.recognized_regular_hours, 5, places=2)
        self.assertAlmostEqual(attendance.payroll_regular_hours, 5, places=2)
