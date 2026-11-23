# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo.exceptions import AccessError, UserError
from odoo import fields
from odoo.fields import Date
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestHrAttendanceKpi(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.location = cls.env["hr.attendance.location"].create({
            "name": "KPI Test Lot",
            "latitude": 10.8231,
            "longitude": 106.6297,
            "company_id": cls.env.company.id,
        })
        cls.department = cls.env["hr.department"].create({
            "name": "KPI Site",
            "company_id": cls.env.company.id,
            "attendance_location_id": cls.location.id,
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "KPI Worker",
            "department_id": cls.department.id,
        })
        cls.month = Date.today().replace(day=1)
        cls.criterion_uniform = cls.env.ref("hr_attendance_kpi.kpi_criterion_uniform")
        cls.criterion_late = cls.env.ref("hr_attendance_kpi.kpi_criterion_late")
        cls.criterion_safety = cls.env.ref("hr_attendance_kpi.kpi_criterion_safety")

        cls.captain = new_test_user(
            cls.env,
            login="kpi_captain",
            groups="hr_attendance_portal.group_hr_attendance_site_captain",
        )
        cls.captain.sudo().write({
            "hr_authorized_department_ids": [(6, 0, [cls.department.id])],
        })
        cls.hr_user = new_test_user(
            cls.env,
            login="kpi_hr",
            groups="hr.group_hr_user",
        )

        cls.sheet = cls.env["hr.kpi.monthly.sheet"].create({
            "department_id": cls.department.id,
            "month_date": cls.month,
        })
        cls.line = cls.sheet.employee_ids.filtered(lambda l: l.employee_id == cls.employee)
        assert cls.line, "Expected employee line on KPI sheet"

    def setUp(self):
        super().setUp()
        self.addCleanup(self.env.registry.clear_cache)

    def _daily_fail(self, day, criterion, note=False):
        Daily = self.env["hr.kpi.daily.line"]
        line = Daily.search([
            ("monthly_employee_id", "=", self.line.id),
            ("date", "=", day),
            ("criterion_id", "=", criterion.id),
        ], limit=1)
        if not line:
            line = Daily.create({
                "monthly_employee_id": self.line.id,
                "date": day,
                "criterion_id": criterion.id,
                "is_fail": True,
                "note": note,
            })
        else:
            line.write({"is_fail": True, "note": note or line.note})
        return line

    def test_tiered_uniform_three_hits_caps_at_twenty(self):
        for offset in range(3):
            self._daily_fail(self.month + relativedelta(days=offset), self.criterion_uniform)
        self.line.action_recompute()
        self.assertEqual(self.line.group_c_percent, 20.0)
        self.assertEqual(self.line.kpi_remaining_percent, 80.0)

    def test_manual_ab_and_rollup_total_capped(self):
        self.line.write({"manual_a_percent": 15, "manual_b_percent": 10})
        self._daily_fail(self.month, self.criterion_late)
        self.line.action_recompute()
        self.assertEqual(self.line.group_d_percent, 20.0)
        self.assertEqual(self.line.total_deduction_percent, 45.0)

    def test_hr_lock_blocks_captain_edits(self):
        self.sheet.with_user(self.hr_user).action_hr_lock()
        with self.assertRaises(UserError):
            self.line.with_user(self.captain).write({"manual_a_percent": 5})

    def test_deadline_blocks_captain_after_lock_day(self):
        self.env.company.kpi_lock_day = 1
        past_month = (Date.today() - relativedelta(months=2)).replace(day=1)
        old_sheet = self.env["hr.kpi.monthly.sheet"].create({
            "department_id": self.department.id,
            "month_date": past_month,
        })
        emp_line = old_sheet.employee_ids[0]
        with self.assertRaises(UserError):
            emp_line.with_user(self.captain).write({"manual_b_percent": 5})

    def test_wizard_syncs_month_grid(self):
        wizard = self.env["hr.kpi.daily.wizard"].create({
            "department_id": self.department.id,
            "month_date": self.month,
            "employee_id": self.employee.id,
        })
        wizard.action_open_daily_grid()
        count = self.env["hr.kpi.daily.line"].search_count([
            ("monthly_employee_id", "=", self.line.id),
        ])
        days_in_month = (self.month + relativedelta(months=1, days=-1)).day
        criteria_count = self.env["hr.kpi.criterion"].search_count(
            self.env["hr.kpi.criterion"]._daily_criteria_domain()
        )
        self.assertEqual(count, days_in_month * criteria_count)

    def test_export_xlsx_sets_binary(self):
        self.line.write({"manual_a_percent": 5, "manual_a_note": "Test case"})
        self.sheet.action_export_xlsx()
        self.assertTrue(self.sheet.export_file)
        self.assertTrue(self.sheet.export_file_name.endswith(".xlsx"))

    def test_captain_cannot_hr_lock(self):
        with self.assertRaises(AccessError):
            self.sheet.with_user(self.captain).action_hr_lock()

    def test_hub_onchange_day_lines_without_saved_hub(self):
        hub = self.env["hr.kpi.hub"].with_user(self.captain).new({
            "month_date": self.month,
        })
        hub.department_id = self.department
        hub._onchange_filters()
        days_in_month = (self.month + relativedelta(months=1, days=-1)).day
        self.assertEqual(len(hub.day_line_ids), days_in_month)
        self.assertTrue(all(line.hub_id == hub for line in hub.day_line_ids))

    def test_hub_day_sync(self):
        hub = self.env["hr.kpi.hub"].with_user(self.captain).create({
            "department_id": self.department.id,
            "month_date": self.month,
        })
        self.assertTrue(hub.sheet_id)
        days_in_month = (self.month + relativedelta(months=1, days=-1)).day
        self.assertEqual(len(hub.day_line_ids), days_in_month)
        day_line = hub.day_line_ids.filtered(lambda l: l.date == self.month)
        action = day_line.action_open_day()
        self.assertEqual(action["res_model"], "hr.kpi.daily.line")
        self.assertIn(("is_fail", "=", True), action["domain"])
        count = self.env["hr.kpi.daily.line"].search_count(action["domain"])
        self.assertEqual(count, 0)

    def test_hub_open_day_without_manual_save(self):
        hub = self.env["hr.kpi.hub"].with_user(self.captain).new({
            "month_date": self.month,
        })
        hub.department_id = self.department
        hub._onchange_filters()
        self.assertFalse(hub.exists())
        day_line = hub.day_line_ids.filtered(lambda line: line.date == self.month)
        self.assertEqual(len(day_line), 1)
        action = day_line.action_open_day()
        self.assertEqual(action["res_model"], "hr.kpi.daily.line")
        persisted = self.env["hr.kpi.hub"].search(
            [
                ("department_id", "=", self.department.id),
                ("month_date", "=", self.month),
            ],
            order="id desc",
            limit=1,
        )
        self.assertTrue(persisted)
        self.assertTrue(persisted.sheet_id)
        count = self.env["hr.kpi.daily.line"].search_count(action["domain"])
        self.assertEqual(count, 0)

    def test_inline_daily_line_create(self):
        hub = self.env["hr.kpi.hub"].with_user(self.captain).create({
            "department_id": self.department.id,
            "month_date": self.month,
        })
        Daily = self.env["hr.kpi.daily.line"].with_user(self.captain)
        line = Daily.with_context(
            kpi_sheet_id=hub.sheet_id.id,
            kpi_hub_date=fields.Date.to_string(self.month),
        ).create({
            "employee_id": self.employee.id,
            "date": self.month,
            "criterion_id": self.criterion_uniform.id,
            "note": "Inline entry",
        })
        self.assertTrue(line.is_fail)
        self.assertEqual(line.note, "Inline entry")
        self.assertEqual(line.employee_id, self.employee)

    def test_daily_entry_wizard_creates_fail_line(self):
        hub = self.env["hr.kpi.hub"].with_user(self.captain).create({
            "department_id": self.department.id,
            "month_date": self.month,
        })
        entry = self.env["hr.kpi.daily.entry"].create({
            "sheet_id": hub.sheet_id.id,
            "date": self.month,
            "employee_id": self.employee.id,
            "criterion_id": self.criterion_uniform.id,
            "note": "Không mặc đồng phục",
        })
        entry.action_save()
        line = self.env["hr.kpi.daily.line"].search([
            ("sheet_id", "=", hub.sheet_id.id),
            ("date", "=", self.month),
            ("employee_id", "=", self.employee.id),
            ("criterion_id", "=", self.criterion_uniform.id),
        ], limit=1)
        self.assertTrue(line.is_fail)
        self.assertEqual(line.note, "Không mặc đồng phục")
        self.line.action_recompute()
        self.assertGreater(self.line.group_c_percent, 0)

    def test_action_open_kpi_hub_creates_record(self):
        action = self.env["hr.kpi.hub"].with_user(self.captain).action_open_kpi_hub()
        hub = self.env["hr.kpi.hub"].browse(action["res_id"])
        self.assertTrue(hub.exists())
        self.assertTrue(hub.month_date)

    def test_captain_sees_kpi_menu(self):
        Menu = self.env["ir.ui.menu"].with_user(self.captain)
        kpi_menu = self.env.ref("hr_attendance_kpi.menu_hr_kpi_hub")
        visible = Menu._visible_menu_ids()
        self.assertIn(kpi_menu.id, visible)

    def test_deduction_for_hits_tiered_below_threshold(self):
        self.assertEqual(self.criterion_uniform._deduction_for_hits(2), 10.0)
        self.assertEqual(self.criterion_late._deduction_for_hits(1), 20.0)

    def test_ab_criteria_in_daily_domain(self):
        domain = self.env["hr.kpi.criterion"]._daily_criteria_domain()
        codes = set(
            self.env["hr.kpi.criterion"].search(domain).mapped("code")
        )
        self.assertIn("A_SAFETY", codes)
        self.assertIn("B_SKILL", codes)
        self.assertEqual(len(codes), 13)

    def test_daily_safety_rollup_group_a(self):
        self._daily_fail(self.month, self.criterion_safety)
        self.line.action_recompute()
        self.assertEqual(self.line.group_a_percent, 20.0)