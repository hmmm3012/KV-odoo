# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from io import BytesIO

from openpyxl import load_workbook

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from .common import AttendancePortalMixin


@tagged("post_install", "-at_install")
class TestAttendanceTimesheet(AttendancePortalMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.attendance_standard_hours = 8.0
        cls.company.attendance_overtime_cap_hours = 4.0
        cls.captain = new_test_user(
            cls.env,
            login="timesheet_captain",
            groups="hr_attendance_portal.group_hr_attendance_site_captain",
        )
        cls.captain.tz = "Asia/Ho_Chi_Minh"
        cls.captain.hr_authorized_department_ids = cls.department
        cls.support_department = cls.env["hr.department"].create({
            "name": "Support Team",
            "company_id": cls.company.id,
        })
        cls.other_department = cls.env["hr.department"].create({
            "name": "Other Lot",
            "company_id": cls.company.id,
        })
        cls.company.employee_properties_definition = [{
            "name": "test_work_shift",
            "type": "selection",
            "string": "Ca làm việc",
            "selection": [
                ["day", "Ca ngày"],
                ["night", "Ca đêm"],
            ],
        }]
        cls.mobile_tag = cls.env["hr.employee.category"].search([("name", "=", "CĐCĐ")], limit=1)
        if not cls.mobile_tag:
            cls.mobile_tag = cls.env["hr.employee.category"].create({"name": "CĐCĐ"})
        cls.idle = cls.env["hr.employee"].create({
            "name": "An Idle",
            "emp_code": "KV-BCC-IDLE",
            "pin": "1357",
            "company_id": cls.company.id,
            "department_id": cls.department.id,
        })
        cls.employee.name = "Mai Official"
        cls.night_employee = cls.env["hr.employee"].create({
            "name": "Nam Night",
            "emp_code": "KV-BCC-NIGHT",
            "pin": "1357",
            "company_id": cls.company.id,
            "department_id": cls.department.id,
            "employee_properties": {"test_work_shift": "night"},
        })
        cls.mobile_employee = cls.env["hr.employee"].create({
            "name": "Cuong Mobile",
            "emp_code": "KV-BCC-MOB",
            "pin": "1357",
            "company_id": cls.company.id,
            "department_id": cls.department.id,
            "category_ids": [(4, cls.mobile_tag.id)],
        })
        cls.support = cls.env["hr.employee"].create({
            "name": "Binh Support",
            "emp_code": "KV-BCC-SUP",
            "pin": "1357",
            "company_id": cls.company.id,
            "department_id": cls.support_department.id,
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

    def test_timesheet_splits_official_and_support(self):
        day = datetime(2026, 9, 1, 1, 0, 0)
        self._shift(self.employee, day, 8, self.department)
        denied = self._shift(self.employee, day + timedelta(days=1), 6, self.department)
        denied.action_deny_session("absent")
        overtime = self._shift(self.employee, day + timedelta(days=1, hours=6), 10, self.department)
        overtime.action_captain_overtime(2, "peak")
        self._shift(self.support, day, 4, self.department)
        self._shift(self.employee, day + timedelta(hours=8), 8, self.other_department)
        # Night-property staff punched in daytime hours still land in Ca Đêm.
        self._shift(self.night_employee, day + timedelta(hours=8), 8, self.department)
        self._shift(self.mobile_employee, day, 5, self.department)

        wizard = self.env["hr.attendance.timesheet.wizard"].with_user(self.captain).create({
            "department_id": self.department.id,
            "date_from": fields.Date.to_date("2026-09-01"),
            "date_to": fields.Date.to_date("2026-09-02"),
        })
        payload = wizard._prepare_timesheet()
        self.assertEqual([row["name"] for row in payload["official_day"]], ["An Idle", "Mai Official"])
        self.assertEqual([row["name"] for row in payload["official_night"]], ["Nam Night"])
        self.assertEqual([row["name"] for row in payload["mobile_day"]], ["Cuong Mobile"])
        self.assertEqual(payload["mobile_night"], [])
        self.assertEqual([row["name"] for row in payload["support_day"]], ["Binh Support"])
        self.assertEqual(payload["support_night"], [])

        idle, official = payload["official_day"]
        self.assertEqual(idle["worked_days"], 0)
        self.assertEqual(idle["total"], 0)
        self.assertEqual(official["days"], [8, 10])
        self.assertEqual(official["regular"], 16)
        self.assertEqual(official["overtime"], 2)
        self.assertEqual(official["total"], 18)
        self.assertEqual(official["worked_days"], 2)
        self.assertEqual(official["shift"], "Ca Ngày")
        night = payload["official_night"][0]
        self.assertEqual(night["days"], [8, 0])
        self.assertEqual(night["shift"], "Ca Đêm")
        mobile = payload["mobile_day"][0]
        self.assertEqual(mobile["days"], [5, 0])
        self.assertEqual(mobile["total"], 5)
        support = payload["support_day"][0]
        self.assertEqual(support["days"], [4, 0])
        self.assertEqual(support["regular"], 4)
        self.assertEqual(support["worked_days"], 1)
        self.assertEqual(support["support_site"], "Support Team")
        self.assertEqual(support["code"], "KV-BCC-SUP")

        site_totals = wizard._timesheet_site_totals(payload)
        self.assertEqual(site_totals["regular"], 33)
        self.assertEqual(site_totals["overtime"], 2)
        self.assertEqual(site_totals["total"], 35)
        self.assertEqual(site_totals["days"], [25, 10])
        self.assertEqual(site_totals["people_count"], 4)

        preview = wizard._render_preview_html()
        self.assertIn("BẢNG CHẤM CÔNG", preview)
        self.assertIn("Mai Official", preview)
        self.assertIn("Binh Support", preview)
        self.assertIn("Cuong Mobile", preview)
        self.assertIn("Cơ động Ca Ngày", preview)
        self.assertIn("kv-timesheet-scroll", preview)
        self.assertIn("Tổng giờ", preview)
        self.assertNotIn("Tổng giờ công cả bãi", preview)
        self.assertIn("Tổng cả bãi", preview)
        wizard.action_preview()
        self.assertTrue(wizard.preview_html)

        workbook = load_workbook(BytesIO(wizard._render_xlsx()))
        sheet = workbook.active
        values = [cell.value for row in sheet.iter_rows() for cell in row]
        self.assertIn("T3", values)
        self.assertIn("T4", values)
        self.assertIn("Ca Ngày", values)
        self.assertIn("Ca Đêm", values)
        self.assertIn("Cơ động Ca Ngày", values)
        self.assertIn("Cơ động Ca Đêm", values)
        self.assertIn("Đến hỗ trợ Ca Ngày", values)
        self.assertIn("Đến hỗ trợ Ca Đêm", values)
        self.assertIn("Ghi chú Phụ Cấp", values)
        self.assertIn("Tổng giờ Công", values)
        self.assertFalse(any(isinstance(value, str) and "Tổng giờ công cả bãi" in value for value in values))
        self.assertIn("Tổng cả bãi", values)
        weekday_above_first_day = False
        for row in sheet.iter_rows():
            for cell in row:
                value = cell.value
                if getattr(value, "year", None) == 2026 and value.month == 9 and value.day == 1:
                    self.assertEqual(sheet.cell(cell.row - 1, cell.column).value, "T3")
                    weekday_above_first_day = True
        self.assertTrue(weekday_above_first_day)

    def test_timesheet_row_order_is_saved_per_lot(self):
        day = datetime(2026, 9, 1, 1, 0, 0)
        self._shift(self.employee, day, 8, self.department)
        self._shift(self.idle, day, 8, self.department)
        wizard = self.env["hr.attendance.timesheet.wizard"].with_user(self.captain)
        wizard.save_row_order(self.department.id, [self.employee.id, self.idle.id])

        record = wizard.create({
            "department_id": self.department.id,
            "date_from": fields.Date.to_date("2026-09-01"),
            "date_to": fields.Date.to_date("2026-09-01"),
        })
        payload = record._prepare_timesheet()
        self.assertEqual(
            [row["name"] for row in payload["official_day"]],
            ["Mai Official", "An Idle"],
        )

        record.action_reset_row_order()
        payload = record._prepare_timesheet()
        self.assertEqual(
            [row["name"] for row in payload["official_day"]],
            ["An Idle", "Mai Official"],
        )
        self.assertFalse(self.env["hr.attendance.timesheet.row.order"].search([
            ("department_id", "=", self.department.id),
        ]))

    def test_merge_mobile_employee_tags(self):
        Category = self.env["hr.employee.category"]
        duplicate = Category.create({"name": "cđcd"})
        ascii_tag = Category.create({"name": "CDCD"})
        other = Category.search([("name", "=", "CĐCT")], limit=1) or Category.create({"name": "CĐCT"})
        holder = self.env["hr.employee"].create({
            "name": "Tag Holder",
            "emp_code": "KV-BCC-TAG",
            "pin": "1357",
            "company_id": self.company.id,
            "department_id": self.department.id,
            "category_ids": [(6, 0, [duplicate.id, ascii_tag.id, other.id])],
        })
        wizard = self.env["hr.attendance.timesheet.wizard"]
        canonical = wizard._merge_mobile_employee_tags()
        self.assertEqual(canonical.name, "CĐCĐ")
        self.assertFalse(duplicate.exists())
        self.assertFalse(ascii_tag.exists())
        self.assertTrue(other.exists())
        self.assertEqual(holder.category_ids, canonical | other)

    def test_support_home_lot_hours_do_not_appear_on_helped_lot(self):
        """One support day must not inherit the helper's other-lot hours."""
        day = datetime(2026, 9, 1, 1, 0, 0)
        self._shift(self.support, day, 8, self.support_department)
        self._shift(self.support, day + timedelta(days=1), 4, self.department)
        self._shift(self.support, day + timedelta(days=2), 8, self.other_department)

        wizard = self.env["hr.attendance.timesheet.wizard"].with_user(self.captain).create({
            "department_id": self.department.id,
            "date_from": fields.Date.to_date("2026-09-01"),
            "date_to": fields.Date.to_date("2026-09-03"),
        })
        payload = wizard._prepare_timesheet()
        self.assertEqual([row["name"] for row in payload["support_day"]], ["Binh Support"])
        support = payload["support_day"][0]
        self.assertEqual(support["days"], [0, 4, 0])
        self.assertEqual(support["total"], 4)
        self.assertEqual(support["worked_days"], 1)

    def test_timesheet_highlights_half_hour_day_cells(self):
        day = datetime(2026, 9, 1, 1, 0, 0)
        self._shift(self.employee, day, 7.5, self.department)
        self._shift(self.employee, day + timedelta(days=1), 8, self.department)
        wizard = self.env["hr.attendance.timesheet.wizard"].with_user(self.captain).create({
            "department_id": self.department.id,
            "date_from": fields.Date.to_date("2026-09-01"),
            "date_to": fields.Date.to_date("2026-09-02"),
        })
        payload = wizard._prepare_timesheet()
        official = payload["official_day"][-1]
        self.assertEqual(official["days"][0], 7.5)
        self.assertEqual(official["days"][1], 8)
        self.assertTrue(wizard._is_half_hour(7.5))
        self.assertFalse(wizard._is_half_hour(8))
        preview = wizard._render_preview_html()
        self.assertIn("kv-half", preview)
        self.assertIn("Ô vàng = giờ lẻ (.5)", preview)
        self.assertRegex(preview, r'class="kv-day kv-num kv-half">7\.5</td>')

    def test_timesheet_rejects_umbrella_parking_group(self):
        parent = self.env["hr.department"].create({
            "name": "All Lots",
            "company_id": self.company.id,
        })
        self.department.parent_id = parent
        self.other_department.parent_id = parent
        self.other_department.attendance_location_id = self.env["hr.attendance.location"].create({
            "name": "Other Lot Gate",
            "company_id": self.company.id,
            "latitude": 10.8,
            "longitude": 106.8,
            "allowed_radius_meters": 100,
            "max_gps_accuracy_meters": 80,
        })
        wizard = self.env["hr.attendance.timesheet.wizard"].create({
            "department_id": parent.id,
            "date_from": fields.Date.to_date("2026-09-01"),
            "date_to": fields.Date.to_date("2026-09-02"),
        })
        with self.assertRaises(UserError):
            wizard._prepare_timesheet()

    def test_export_rejects_an_inverted_or_long_range(self):
        wizard = self.env["hr.attendance.timesheet.wizard"].create({
            "department_id": self.department.id,
            "date_from": fields.Date.to_date("2026-09-02"),
            "date_to": fields.Date.to_date("2026-09-01"),
        })
        with self.assertRaises(UserError):
            wizard.action_export()
        wizard.date_to = fields.Date.to_date("2026-12-01")
        with self.assertRaises(UserError):
            wizard.action_export()

    def test_captain_cannot_export_another_lot(self):
        wizard = self.env["hr.attendance.timesheet.wizard"].with_user(self.captain).create({
            "department_id": self.other_department.id,
            "date_from": fields.Date.to_date("2026-09-01"),
            "date_to": fields.Date.to_date("2026-09-02"),
        })
        with self.assertRaises(AccessError):
            wizard.action_export()
