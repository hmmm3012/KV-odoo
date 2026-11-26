# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from .common import AttendancePortalMixin


@tagged("post_install", "-at_install")
class TestDailyAllowance(AttendancePortalMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.attendance_standard_hours = 8.0
        cls.company.attendance_overtime_cap_hours = 4.0
        cls.captain = new_test_user(
            cls.env,
            login="allowance_captain",
            groups="hr_attendance_portal.group_hr_attendance_site_captain",
        )
        cls.captain.tz = "Asia/Ho_Chi_Minh"
        cls.other_captain = new_test_user(
            cls.env,
            login="allowance_other_captain",
            groups="hr_attendance_portal.group_hr_attendance_site_captain",
        )
        cls.srcs = cls.env["hr.department"].create({
            "name": "SRCS",
            "company_id": cls.company.id,
        })
        cls.sgp = cls.env["hr.department"].create({
            "name": "Sài Gòn Pearl",
            "company_id": cls.company.id,
        })
        cls.other = cls.env["hr.department"].create({
            "name": "Other Lot",
            "company_id": cls.company.id,
        })
        cls.captain.hr_authorized_department_ids = cls.department | cls.srcs | cls.sgp
        cls.other_captain.hr_authorized_department_ids = cls.other
        cls.employee.name = "Mai Official"
        cls.idle = cls.env["hr.employee"].create({
            "name": "An Idle",
            "emp_code": "KV-PC-IDLE",
            "pin": "1357",
            "company_id": cls.company.id,
            "department_id": cls.department.id,
        })

    def _shift(self, employee, start, hours, department):
        attendance = self.env["hr.attendance"].create({
            "employee_id": employee.id,
            "check_in": start,
            "in_department_id": department.id,
            "in_location_id": department.attendance_location_id.id,
        })
        attendance.with_context(attendance_original_punch=True).write({
            "check_out": start + timedelta(hours=hours),
        })
        return attendance

    def _wizard(self, department, day="2026-09-01"):
        return self.env["hr.attendance.timesheet.wizard"].create({
            "department_id": department.id,
            "date_from": fields.Date.to_date("2026-09-01"),
            "date_to": fields.Date.to_date("2026-09-02"),
            "allowance_date": fields.Date.to_date(day),
        })

    def _save(self, department, employee, allowance_type, day="2026-09-01", user=None):
        wizard = self.env["hr.attendance.timesheet.wizard"]
        if user:
            wizard = wizard.with_user(user)
        return wizard.save_daily_allowances(
            department.id,
            day,
            [{"employee_id": employee.id, "allowance_type": allowance_type}],
            "2026-09-01",
            "2026-09-02",
        )

    def test_workplace_codes_match_short_name_and_full_name(self):
        Allowance = self.env["hr.attendance.daily.allowance"]
        self.assertEqual(Allowance._workplace_codes(self.department), set())
        self.assertEqual(Allowance._workplace_codes(self.srcs), {"SRCS"})
        self.assertEqual(Allowance._workplace_codes(self.sgp), {"SGP"})
        sunrise = self.env["hr.department"].create({
            "name": "Sunrise City South",
            "company_id": self.company.id,
        })
        self.assertIn("SRCS", Allowance._workplace_codes(sunrise))
        self.assertNotIn("sidewalk", Allowance._allowed_type_keys(self.srcs))
        self.assertIn("gate_both", Allowance._allowed_type_keys(self.srcs))
        self.assertIn("sidewalk", Allowance._allowed_type_keys(self.sgp))
        self.assertNotIn("gate_both", Allowance._allowed_type_keys(self.sgp))

    def test_day_grid_lists_who_worked_and_saves_one_allowance(self):
        day = datetime(2026, 9, 1, 1, 0, 0)
        self._shift(self.employee, day, 4, self.department)
        self._shift(self.employee, day + timedelta(hours=5), 3, self.department)
        denied = self._shift(self.idle, day, 6, self.department)
        denied.action_deny_session("absent")

        wizard = self._wizard(self.department)
        html = str(wizard._render_allowance_grid_html())
        self.assertEqual(html.count('data-employee-id="%s"' % self.employee.id), 1)
        self.assertNotIn("An Idle", html)
        self.assertNotIn('value="sidewalk"', html)
        self.assertNotIn('value="gate_both"', html)
        self.assertIn("PC CO", html)

        summary = self._save(self.department, self.employee, "co", user=self.captain)
        self.assertIn("Mai Official", summary)
        self.assertIn('class="kv-num">1<', summary)
        stored = self.env["hr.attendance.daily.allowance"].search([
            ("employee_id", "=", self.employee.id),
            ("department_id", "=", self.department.id),
            ("date", "=", "2026-09-01"),
        ])
        self.assertEqual(stored.allowance_type, "co")
        self.assertEqual(len(stored), 1)

        self._save(self.department, self.employee, "gate_out", user=self.captain)
        stored = self.env["hr.attendance.daily.allowance"].search([
            ("employee_id", "=", self.employee.id),
            ("department_id", "=", self.department.id),
            ("date", "=", "2026-09-01"),
        ])
        self.assertEqual(stored.allowance_type, "gate_out")

        self._save(self.department, self.employee, False, user=self.captain)
        self.assertFalse(self.env["hr.attendance.daily.allowance"].search([
            ("employee_id", "=", self.employee.id),
            ("date", "=", "2026-09-01"),
        ]))

    def test_site_only_types_and_people_without_hours(self):
        day = datetime(2026, 9, 1, 1, 0, 0)
        self._shift(self.employee, day, 8, self.srcs)
        with self.assertRaises(UserError):
            self._save(self.srcs, self.employee, "sidewalk")
        self._save(self.srcs, self.employee, "gate_both")
        self.assertEqual(
            self.env["hr.attendance.daily.allowance"].search([
                ("department_id", "=", self.srcs.id),
            ]).allowance_type,
            "gate_both",
        )

        self._shift(self.employee, day + timedelta(days=1), 8, self.sgp)
        with self.assertRaises(UserError):
            self._save(self.sgp, self.employee, "gate_both", day="2026-09-02")
        summary = self._save(self.sgp, self.employee, "sidewalk", day="2026-09-02")
        self.assertIn("PC vỉa hè", summary)
        self.assertIn('data-date="2026-09-02"', summary)

        with self.assertRaises(UserError):
            self._save(self.department, self.idle, "co")

    def test_other_captain_cannot_save(self):
        day = datetime(2026, 9, 1, 1, 0, 0)
        self._shift(self.employee, day, 8, self.department)
        with self.assertRaises(AccessError):
            self._save(self.department, self.employee, "co", user=self.other_captain)

    def test_stale_allowance_can_be_cleared(self):
        self.env["hr.attendance.daily.allowance"].create({
            "employee_id": self.idle.id,
            "department_id": self.department.id,
            "date": "2026-09-01",
            "allowance_type": "co",
        })
        html = str(self._wizard(self.department)._render_allowance_grid_html())
        self.assertIn("An Idle", html)
        self.assertIn("Không còn giờ", html)
        with self.assertRaises(UserError):
            self._save(self.department, self.idle, "gate_in")
        self._save(self.department, self.idle, False)
        self.assertFalse(self.env["hr.attendance.daily.allowance"].search([
            ("employee_id", "=", self.idle.id),
        ]))
