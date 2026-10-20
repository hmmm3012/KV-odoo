# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError
from odoo.fields import Date
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestHrDepartmentAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env["hr.department"].create({"name": "Site A"})
        cls.team = cls.env["hr.department"].create({
            "name": "Site A Team",
            "parent_id": cls.site.id,
        })
        cls.other = cls.env["hr.department"].create({"name": "Site B"})
        cls.inside = cls.env["hr.employee"].create({
            "name": "Inside Site",
            "department_id": cls.site.id,
        })
        cls.child_employee = cls.env["hr.employee"].create({
            "name": "Child Team",
            "department_id": cls.team.id,
        })
        cls.outside = cls.env["hr.employee"].create({
            "name": "Outside Site",
            "department_id": cls.other.id,
        })
        cls.hr_user = new_test_user(
            cls.env,
            login="dept_hr_site_a",
            groups="hr_contract.group_hr_contract_manager,hr_attendance.group_hr_attendance_manager",
        )
        cls.hr_user.sudo().write({
            "hr_authorized_department_ids": [(6, 0, [cls.site.id])],
        })
        cls.company_hr = new_test_user(
            cls.env,
            login="dept_hr_company",
            groups="hr.group_hr_user",
        )

    def setUp(self):
        super().setUp()
        self.addCleanup(self.env.registry.clear_cache)

    def test_restricted_user_sees_department_and_children_only(self):
        employees = self.env["hr.employee"].with_user(self.hr_user).search([
            ("id", "in", [self.inside.id, self.child_employee.id, self.outside.id]),
        ])
        self.assertEqual(set(employees.ids), {self.inside.id, self.child_employee.id})
        departments = self.env["hr.department"].with_user(self.hr_user).search([
            ("id", "in", [self.site.id, self.team.id, self.other.id]),
        ])
        self.assertEqual(set(departments.ids), {self.site.id, self.team.id})

    def test_company_wide_user_is_not_limited(self):
        employees = self.env["hr.employee"].with_user(self.company_hr).search([
            ("id", "in", [self.inside.id, self.outside.id]),
        ])
        self.assertEqual(set(employees.ids), {self.inside.id, self.outside.id})

    def test_cannot_read_or_create_outside_department(self):
        Employee = self.env["hr.employee"].with_user(self.hr_user)
        with self.assertRaises(AccessError):
            Employee.browse(self.outside.id).read(["name"])
        with self.assertRaises(AccessError):
            Employee.create({
                "name": "Other Site Hire",
                "department_id": self.other.id,
            })
        created = Employee.create({
            "name": "Site Hire",
            "department_id": self.team.id,
        })
        self.assertEqual(created.department_id, self.team)

    def test_attendance_and_contract_follow_the_employee_department(self):
        Attendance = self.env["hr.attendance"].sudo()
        inside_attendance = Attendance.create({"employee_id": self.inside.id})
        outside_attendance = Attendance.create({"employee_id": self.outside.id})
        visible = self.env["hr.attendance"].with_user(self.hr_user).search([
            ("id", "in", [inside_attendance.id, outside_attendance.id]),
        ])
        self.assertEqual(visible, inside_attendance)
        with self.assertRaises(AccessError):
            self.env["hr.contract"].with_user(self.hr_user).create({
                "name": "Outside contract",
                "employee_id": self.outside.id,
                "wage": 1,
                "date_start": Date.today(),
            })
        contract = self.env["hr.contract"].with_user(self.hr_user).create({
            "name": "Inside contract",
            "employee_id": self.inside.id,
            "wage": 1,
            "date_start": Date.today(),
        })
        self.assertEqual(contract.employee_id, self.inside)

    def test_public_directory_and_own_employee_outside_the_site(self):
        public_outside = self.env["hr.employee.public"].with_user(self.hr_user).search([
            ("id", "=", self.outside.id),
        ])
        self.assertFalse(public_outside)
        own = self.env["hr.employee"].create({
            "name": "HR Own Record",
            "user_id": self.hr_user.id,
            "department_id": self.other.id,
        })
        self.env.registry.clear_cache()
        found = self.env["hr.employee"].with_user(self.hr_user).search([
            ("id", "=", own.id),
        ])
        self.assertEqual(found, own)

    def test_sudo_is_not_limited(self):
        employees = self.env["hr.employee"].with_user(self.hr_user).sudo().search([
            ("id", "in", [self.inside.id, self.outside.id]),
        ])
        self.assertEqual(set(employees.ids), {self.inside.id, self.outside.id})
