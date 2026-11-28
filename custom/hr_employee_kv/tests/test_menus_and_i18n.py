# -*- coding: utf-8 -*-
"""Smoke checks for menus, the employee form, and Vietnamese labels."""
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestMenusAndI18n(TransactionCase):
    def _menu(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def test_discuss_and_calendar_root_menus_are_inactive(self):
        discuss = self._menu("mail.menu_root_discuss")
        calendar = self._menu("calendar.mail_menu_calendar")
        self.assertTrue(discuss, "mail.menu_root_discuss should exist")
        self.assertTrue(calendar, "calendar.mail_menu_calendar should exist")
        self.assertFalse(discuss.active)
        self.assertFalse(calendar.active)

    def test_main_hr_menus_exist_for_an_officer(self):
        officer = new_test_user(self.env, login="kv_menu_officer", groups="hr.group_hr_user")
        menus = self.env["ir.ui.menu"].with_user(officer).load_menus(debug=False)
        root_ids = menus.get("root_id") and menus["root_id"].get("children") or []
        # load_menus structure varies slightly; also search visible menus
        names = set(self.env["ir.ui.menu"].with_user(officer).search([("parent_id", "=", False)]).mapped("name"))
        # English or Vietnamese, depending on the test user's lang
        joined = " | ".join(sorted(names))
        self.assertTrue(
            any(n in joined for n in ("Employees", "Nhân viên", "Attendances", "Chấm công")),
            f"expected HR menus, got {joined!r}",
        )

    def test_employee_form_has_id_card_autofill_widget(self):
        view = self.env["ir.ui.view"].browse(
            self.env["hr.employee"].get_view(view_type="form")["id"]
        ) if False else None
        arch = self.env["hr.employee"].get_view(view_type="form")["arch"]
        self.assertIn("kv_id_card_autofill", arch)
        self.assertIn("o_kv_id_card_autofill_row", arch)

    def test_employee_form_tab_renamed_to_contract_and_salary(self):
        arch = self.env["hr.employee"].get_view(view_type="form")["arch"]
        self.assertIn("Hợp đồng &amp; Lương", arch)

    def test_autofill_widget_is_limited_to_hr_officers(self):
        # get_view() compiles group attributes away; inspect the source inherit.
        views = self.env["ir.ui.view"].search([("arch_db", "ilike", "kv_id_card_autofill")])
        self.assertTrue(views, "expected an inherited view that adds kv_id_card_autofill")
        self.assertTrue(
            any("hr.group_hr_user" in (view.arch or "") for view in views),
            "Tự nhập thông tin must stay limited to hr.group_hr_user",
        )
        captain = new_test_user(
            self.env,
            login="kv_menu_captain",
            groups="hr_attendance_portal.group_hr_attendance_site_captain",
        )
        self.assertFalse(captain.has_group("hr.group_hr_user"))
