# -*- coding: utf-8 -*-

from odoo import api, models, tools
from odoo.osv import expression
from odoo.tools import frozendict


class ResUsers(models.Model):
    _inherit = "res.users"

    def _hr_site_captain_department_ids(self):
        """Departments this captain may view, including sub-departments.

        Read the relation table directly. The authorized-department field is
        restricted to Settings, and captains must not need that group.
        """
        self.ensure_one()
        self.env.cr.execute(
            """
            SELECT department_id
              FROM res_users_hr_department_rel
             WHERE user_id = %s
            """,
            (self.id,),
        )
        root_ids = [row[0] for row in self.env.cr.fetchall()]
        if not root_ids:
            return []
        return self.env["hr.department"].sudo().search([("id", "child_of", root_ids)]).ids

    def _hr_site_captain_location_ids(self):
        department_ids = self._hr_site_captain_department_ids()
        if not department_ids:
            return []
        return self.env["hr.department"].sudo().browse(department_ids).mapped("attendance_location_id").ids

    def _hr_site_captain_employee_domain(self):
        """Own staff, plus people who punched at this captain's workplace."""
        department_ids = self._hr_site_captain_department_ids()
        location_ids = self._hr_site_captain_location_ids()
        if not department_ids and not location_ids:
            return [("id", "=", 0)]
        domain = [("department_id", "in", department_ids)] if department_ids else []
        if location_ids:
            domain = expression.OR([domain, [
                "|",
                ("attendance_ids.in_location_id", "in", location_ids),
                ("attendance_ids.out_location_id", "in", location_ids),
            ]])
        if department_ids:
            domain = expression.OR([domain, [
                "|",
                ("attendance_ids.in_department_id", "in", department_ids),
                ("attendance_ids.out_department_id", "in", department_ids),
            ]])
        return domain

    def _hr_site_captain_attendance_domain(self):
        department_ids = self._hr_site_captain_department_ids()
        location_ids = self._hr_site_captain_location_ids()
        if not department_ids and not location_ids:
            return [("id", "=", 0)]
        domain = [("employee_id.department_id", "in", department_ids)] if department_ids else []
        if department_ids:
            domain = expression.OR([domain, [
                "|",
                ("in_department_id", "in", department_ids),
                ("out_department_id", "in", department_ids),
            ]])
        if location_ids:
            domain = expression.OR([domain, [
                "|",
                ("in_location_id", "in", location_ids),
                ("out_location_id", "in", location_ids),
            ]])
        return domain

    def _hr_site_captain_event_domain(self):
        department_ids = self._hr_site_captain_department_ids()
        location_ids = self._hr_site_captain_location_ids()
        if not department_ids and not location_ids:
            return [("id", "=", 0)]
        domain = [("employee_id.department_id", "in", department_ids)] if department_ids else []
        if department_ids:
            domain = expression.OR([domain, [("department_id", "in", department_ids)]])
        if location_ids:
            domain = expression.OR([domain, [("location_id", "in", location_ids)]])
        return domain

    def _hr_site_captain_location_domain(self):
        location_ids = self._hr_site_captain_location_ids()
        if not location_ids:
            return [("id", "=", 0)]
        return [("id", "in", location_ids)]

    @api.model
    def _hr_department_access_domain(self, model_name):
        """Let a department limit include punches recorded at that workplace.

        The base rule only matches the employee's own department. A captain
        must also see visitors who checked in or out at their workplace.
        """
        domain = super()._hr_department_access_domain(model_name)
        if not domain or not self.env.user.has_group(
            "hr_attendance_portal.group_hr_attendance_site_captain"
        ):
            return domain
        department_ids = list(self._hr_authorized_department_ids())
        if not department_ids:
            return domain
        if model_name == "hr.attendance":
            return expression.OR([domain, self.env.user._hr_site_captain_attendance_domain()])
        if model_name == "hr.attendance.event":
            return expression.OR([domain, self.env.user._hr_site_captain_event_domain()])
        if model_name == "hr.employee":
            return expression.OR([domain, self.env.user._hr_site_captain_employee_domain()])
        return domain

    @api.model
    @tools.ormcache("self._uid")
    def context_get(self):
        context = dict(super().context_get())
        user = self.env.user
        if user.has_group("hr_attendance_portal.group_hr_attendance_site_captain"):
            context["captain_department_ids"] = user._hr_site_captain_department_ids()
        return frozendict(context)

    def _is_attendance_hr_menu(self):
        """An attendance officer who is not a Settings administrator.

        Settings keeps the full attendance menu. HR accounts only see Overview,
        shifts waiting for HR, verification, and Reporting.
        """
        self.ensure_one()
        return (
            self.has_group("hr_attendance.group_hr_attendance_officer")
            and not self.has_group("base.group_system")
        )

    def _is_attendance_captain_only(self):
        """A department captain who is not also HR, attendance officer, or Settings."""
        self.ensure_one()
        return (
            self.has_group("hr_attendance_portal.group_hr_attendance_site_captain")
            and not self.has_group("base.group_system")
            and not self.has_group("hr.group_hr_user")
            and not self.has_group("hr_attendance.group_hr_attendance_officer")
        )

    @api.model
    def _assign_attendance_captain_home_action(self):
        """Open the department attendance list when a captain signs in."""
        action = self.env.ref(
            "hr_attendance_portal.action_site_captain_attendance",
            raise_if_not_found=False,
        )
        users = self if self else self.search([])
        captains = users.filtered(lambda user: user._is_attendance_captain_only())
        pending = captains.filtered(lambda user: user.action_id.id != action.id)
        if action and pending:
            pending.with_context(skip_captain_home_action=True).sudo().write({
                "action_id": action.id,
            })

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if not self.env.context.get("skip_captain_home_action"):
            users._assign_attendance_captain_home_action()
        return users

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_captain_home_action"):
            self._assign_attendance_captain_home_action()
        return res
