# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools


class ResUsers(models.Model):
    _inherit = "res.users"

    hr_authorized_department_ids = fields.Many2many(
        "hr.department",
        "res_users_hr_department_rel",
        "user_id",
        "department_id",
        string="Authorized Departments",
        groups="base.group_system",
        help="Departments this user may manage, including their sub-departments. "
        "Leave empty to keep company-wide HR access.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if any("hr_authorized_department_ids" in vals for vals in vals_list):
            self._clear_hr_department_access_cache()
        return users

    def write(self, vals):
        res = super().write(vals)
        if "hr_authorized_department_ids" in vals:
            self._clear_hr_department_access_cache()
        return res

    def _clear_hr_department_access_cache(self):
        self.env.flush_all()
        self.env.registry.clear_cache()

    @api.model
    @tools.ormcache("self.env.uid")
    def _hr_authorized_department_ids(self):
        """Root department ids for the current user.

        Read from the relation table so record rules cannot recurse through
        hr.department. An empty result means company-wide access.
        """
        self.env.cr.execute(
            """
            SELECT department_id
              FROM res_users_hr_department_rel
             WHERE user_id = %s
            """,
            (self.env.uid,),
        )
        return tuple(row[0] for row in self.env.cr.fetchall())

    @api.model
    def _hr_department_access_domain(self, model_name, mode="read"):
        """Extra domain applied when this user is limited to departments."""
        department_ids = list(self._hr_authorized_department_ids())
        if not department_ids:
            return []
        user_id = self.env.uid
        in_department = ("department_id", "child_of", department_ids)
        employee_in_department = ("employee_id.department_id", "child_of", department_ids)
        own_employee = [
            "|",
            ("user_id", "=", user_id),
            in_department,
        ]
        own_or_employee = [
            "|",
            ("employee_id.user_id", "=", user_id),
            employee_in_department,
        ]
        # hr.employee _inherits hr.version: the first version is created
        # *before* the employee row exists, so employee_id is empty and a
        # domain that only looks at employee_id.department_id denies a hire
        # into an allowed department. Allow that initial version when its
        # own department_id is in scope; do not use a bare department_id OR
        # (that would let a user attach a version to an out-of-scope employee).
        initial_or_employee_version = [
            "|",
            "|",
            ("employee_id.user_id", "=", user_id),
            employee_in_department,
            "&",
            ("employee_id", "=", False),
            ("department_id", "child_of", department_ids),
        ]
        domains = {
            "hr.employee": own_employee,
            "hr.employee.public": own_employee,
            "hr.department": [("id", "child_of", department_ids)],
            "hr.attendance": own_or_employee,
            # Odoo 19: hr.attendance.overtime -> hr.attendance.overtime.line,
            # hr.contract (+ hr.contract.history) -> hr.version.
            "hr.attendance.overtime.line": own_or_employee,
            "hr.version": initial_or_employee_version,
            "hr.attendance.event": [
                "|",
                "|",
                ("employee_id.user_id", "=", user_id),
                employee_in_department,
                in_department,
            ],
            "hr.attendance.session": own_or_employee,
            "hr.attendance.location": [("linked_department_ids", "child_of", department_ids)],
            "hr.attendance.device": [
                ("location_id.linked_department_ids", "child_of", department_ids)
            ],
        }
        # hr.employee._create pops version_id and calls check_access("create")
        # before the version is linked, so department_id (inherited) is still
        # empty and a record rule would deny a valid hire. Enforce the same
        # scope in hr.employee.create from the submitted values instead.
        if model_name in ("hr.employee", "hr.employee.public") and mode == "create":
            return []
        return domains.get(model_name, [])
