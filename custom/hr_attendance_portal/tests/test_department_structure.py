# -*- coding: utf-8 -*-

import base64
from datetime import date
from io import BytesIO

from freezegun import freeze_time
from openpyxl import load_workbook
from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestDepartmentStructure(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.employee_properties_definition = [{
            "name": "test_work_shift",
            "type": "selection",
            "string": "Ca làm việc",
            "selection": [["day", "Ca ngày"], ["night", "Ca đêm"]],
        }]
        cls.department = cls.env["hr.department"].create({
            "name": "Structure Lot",
            "company_id": cls.company.id,
            "structure_qlbx": 1,
            "structure_cskh": 1,
            "structure_day": 2,
            "structure_night": 1,
        })
        cls.other_department = cls.env["hr.department"].create({
            "name": "Other Structure Lot",
            "company_id": cls.company.id,
        })
        cls.manager_job = cls.env["hr.job"].create({"name": "Lot Manager", "structure_role": "qlbx"})
        cls.staff_job = cls.env["hr.job"].create({"name": "Lot Staff"})

        def employee(name, shift=None, job=None, department=None):
            values = {
                "name": name,
                "company_id": cls.company.id,
                "department_id": (department or cls.department).id,
                "job_id": (job or cls.staff_job).id,
            }
            if shift:
                values["employee_properties"] = {"test_work_shift": shift}
            return cls.env["hr.employee"].create(values)

        cls.manager = employee("Quan Manager", shift="night", job=cls.manager_job)
        cls.day_a = employee("An Day", shift="day")
        cls.day_b = employee("Binh Day", shift="day")
        cls.day_c = employee("Cuong Day", shift="day")
        cls.night = employee("Dung Night", shift="night")
        cls.unassigned = employee("Em Unassigned")
        cls.outsider = employee("Giang Outside", shift="day", department=cls.other_department)

        cls.captain = new_test_user(
            cls.env,
            login="structure_captain",
            groups="hr_attendance_portal.group_hr_attendance_site_captain",
        )
        cls.captain.hr_authorized_department_ids = cls.department

    def test_actual_headcount_uses_job_group_then_work_shift(self):
        dept = self.department
        self.assertEqual(dept.structure_total, 5)
        self.assertEqual(
            (dept.actual_qlbx, dept.actual_cskh, dept.actual_day, dept.actual_night, dept.actual_unassigned),
            (1, 0, 3, 1, 1),
        )
        self.assertEqual(dept.actual_total, 6)
        self.assertEqual(
            (dept.gap_qlbx, dept.gap_cskh, dept.gap_day, dept.gap_night, dept.gap_total),
            (0, -1, 1, 0, 1),
        )

    def test_off_limit_blocks_extra_people_on_the_same_shift(self):
        self.department.off_max_day = 1
        Off = self.env["hr.department.off"]
        first = Off.create({"employee_id": self.day_a.id, "date": date(2026, 12, 1)})
        self.assertEqual(first.department_id, self.department)
        self.assertEqual(first.shift, "day")
        with self.assertRaises(ValidationError):
            Off.create({"employee_id": self.day_b.id, "date": date(2026, 12, 1)})
        night_off = Off.create({"employee_id": self.night.id, "date": date(2026, 12, 1)})
        self.assertEqual(night_off.shift, "night")
        Off.create({"employee_id": self.day_b.id, "date": date(2026, 12, 2)})

    def test_employee_cannot_be_off_twice_on_one_day(self):
        Off = self.env["hr.department.off"]
        Off.create({"employee_id": self.day_a.id, "date": date(2026, 12, 3)})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.cr.savepoint():
            Off.create({"employee_id": self.day_a.id, "date": date(2026, 12, 3)})

    @freeze_time("2026-11-06")
    def test_captain_manages_off_only_in_own_department(self):
        Off = self.env["hr.department.off"]
        foreign = Off.create({"employee_id": self.outsider.id, "date": date(2026, 12, 4)})
        own = Off.with_user(self.captain).create({"employee_id": self.day_c.id, "date": date(2026, 12, 4)})
        self.assertEqual(own.department_id, self.department)
        visible = Off.with_user(self.captain).search([("date", "=", date(2026, 12, 4))])
        self.assertEqual(visible, own)
        with self.assertRaises(AccessError):
            foreign.with_user(self.captain).write({"note": "x"})

    def test_captain_cannot_change_structure(self):
        with self.assertRaises(AccessError):
            self.department.with_user(self.captain).write({"structure_day": 9})

    def test_export_lists_names_by_department_and_shift(self):
        Off = self.env["hr.department.off"]
        Off.create({"employee_id": self.day_a.id, "date": date(2026, 12, 5)})
        Off.create({"employee_id": self.day_b.id, "date": date(2026, 12, 5)})
        Off.create({"employee_id": self.night.id, "date": date(2026, 12, 5)})
        wizard = self.env["hr.department.off.export"].create({
            "date_from": date(2026, 12, 5),
            "date_to": date(2026, 12, 6),
            "department_ids": [(6, 0, self.department.ids)],
        })
        action = wizard.action_export()
        self.assertEqual(action["type"], "ir.actions.act_url")
        sheet = load_workbook(BytesIO(base64.b64decode(wizard.file)))["OFF"]
        self.assertEqual(sheet["B3"].value, "Structure Lot")
        self.assertEqual(sheet["A5"].value, "05/12")
        self.assertEqual(sheet["B5"].value, "An Day, Binh Day")
        self.assertEqual(sheet["C5"].value, "Dung Night")
        self.assertFalse(sheet["B6"].value)

    def _december_offs(self):
        offs = self.env["hr.department.off"].search([
            ("department_id", "=", self.department.id),
            ("date", ">=", date(2026, 12, 1)),
            ("date", "<=", date(2026, 12, 31)),
        ])
        return {(off.employee_id, off.date.day, off.shift) for off in offs}

    def test_calendar_loads_month_with_people_and_offs(self):
        self.department.off_max_day = 2
        self.env["hr.department.off"].create({"employee_id": self.day_a.id, "date": date(2026, 12, 1)})
        data = self.env["hr.department.off"].off_calendar_load(self.department.id, 2026, 12)
        self.assertEqual((data["first_weekday"], data["days_in_month"]), (1, 31))
        self.assertEqual(data["limits"], {"day": 2, "night": 0})
        self.assertEqual(data["offs"], {"2026-12-01": {"day": [self.day_a.id], "night": []}})
        shifts = {row["id"]: row["shift"] for row in data["employees"]}
        self.assertEqual(shifts[self.night.id], "night")
        self.assertEqual(shifts[self.unassigned.id], "")
        self.assertNotIn(self.outsider.id, shifts)

    def test_calendar_save_adds_removes_and_moves_offs(self):
        Off = self.env["hr.department.off"]
        Off.create({"employee_id": self.day_a.id, "date": date(2026, 12, 1)})
        Off.create({"employee_id": self.day_b.id, "date": date(2026, 12, 2)})
        data = Off.off_calendar_save(self.department.id, 2026, 12, {
            "2026-12-01": {"day": [], "night": []},
            "2026-12-02": {"day": [], "night": [self.day_b.id]},
            "2026-12-03": {"day": [self.day_c.id], "night": [self.night.id]},
        })
        self.assertEqual(self._december_offs(), {
            (self.day_b, 2, "night"),
            (self.day_c, 3, "day"),
            (self.night, 3, "night"),
        })
        self.assertEqual(data["offs"]["2026-12-03"], {"day": [self.day_c.id], "night": [self.night.id]})

    def test_calendar_save_rejects_bad_input(self):
        Off = self.env["hr.department.off"]
        with self.assertRaises(UserError):
            Off.off_calendar_save(self.department.id, 2026, 12, {
                "2026-12-01": {"day": [self.unassigned.id], "night": [self.unassigned.id]},
            })
        with self.assertRaises(AccessError):
            Off.off_calendar_save(self.department.id, 2026, 12, {
                "2026-12-01": {"day": [self.outsider.id], "night": []},
            })
        with self.assertRaises(UserError):
            Off.off_calendar_save(self.department.id, 2026, 12, {
                "2027-01-01": {"day": [self.day_a.id], "night": []},
            })
        self.department.off_max_day = 1
        with self.assertRaises(ValidationError), self.cr.savepoint():
            Off.off_calendar_save(self.department.id, 2026, 12, {
                "2026-12-01": {"day": [self.day_a.id, self.day_b.id], "night": []},
            })
        self.assertFalse(self._december_offs())

    def test_calendar_save_rejects_off_already_in_other_department(self):
        Off = self.env["hr.department.off"]
        Off.create({"employee_id": self.day_a.id, "department_id": self.other_department.id, "date": date(2026, 12, 1)})
        with self.assertRaises(UserError):
            Off.off_calendar_save(self.department.id, 2026, 12, {
                "2026-12-01": {"day": [self.day_a.id], "night": []},
            })

    @freeze_time("2026-11-06")
    def test_captain_calendar_is_limited_to_own_departments(self):
        Off = self.env["hr.department.off"].with_user(self.captain)
        self.assertEqual(
            [row["id"] for row in Off.off_calendar_departments()],
            [self.department.id],
        )
        Off.off_calendar_save(self.department.id, 2026, 12, {
            "2026-12-05": {"day": [self.day_a.id], "night": []},
        })
        self.assertEqual(self._december_offs(), {(self.day_a, 5, "day")})
        with self.assertRaises(AccessError):
            Off.off_calendar_load(self.other_department.id, 2026, 12)

    @freeze_time("2026-11-06")
    def test_captain_cannot_change_month_after_lock_day(self):
        Off = self.env["hr.department.off"]
        november = Off.create({"employee_id": self.day_a.id, "date": date(2026, 11, 20)})
        captain_off = Off.with_user(self.captain)
        with self.assertRaises(UserError), self.cr.savepoint():
            captain_off.create({"employee_id": self.day_b.id, "date": date(2026, 11, 21)})
        with self.assertRaises(UserError):
            november.with_user(self.captain).write({"note": "x"})
        with self.assertRaises(UserError):
            november.with_user(self.captain).unlink()
        with self.assertRaises(UserError):
            captain_off.off_calendar_save(self.department.id, 2026, 11, {
                "2026-11-20": {"day": [], "night": []},
            })
        december = captain_off.create({"employee_id": self.day_b.id, "date": date(2026, 12, 1)})
        with self.assertRaises(UserError), self.cr.savepoint():
            december.write({"date": date(2026, 11, 30)})
        lock = captain_off.off_calendar_load(self.department.id, 2026, 11)["lock"]
        self.assertEqual(lock, {"date": "2026-10-27", "last_day": "2026-10-26", "locked": True, "is_hr": False})
        self.assertFalse(captain_off.off_calendar_load(self.department.id, 2026, 12)["lock"]["locked"])

    def test_lock_starts_on_configured_day_and_spares_hr(self):
        self.company.off_schedule_lock_day = 20
        captain_off = self.env["hr.department.off"].with_user(self.captain)
        with freeze_time("2026-11-19"):
            captain_off.create({"employee_id": self.day_a.id, "date": date(2026, 12, 1)})
        with freeze_time("2026-11-20"), self.assertRaises(UserError), self.cr.savepoint():
            captain_off.create({"employee_id": self.day_b.id, "date": date(2026, 12, 2)})
        hr_user = new_test_user(self.env, login="off_hr_user", groups="hr.group_hr_user")
        with freeze_time("2026-11-20"):
            data = self.env["hr.department.off"].with_user(hr_user).off_calendar_save(
                self.department.id, 2026, 12, {"2026-12-02": {"day": [self.day_b.id], "night": []}},
            )
        self.assertEqual(data["lock"]["locked"], True)
        self.assertEqual(data["lock"]["is_hr"], True)
        self.assertEqual(self._december_offs(), {(self.day_b, 2, "day")})
        with self.assertRaises(ValidationError):
            self.company.off_schedule_lock_day = 31
