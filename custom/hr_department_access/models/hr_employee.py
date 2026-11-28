# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.exceptions import AccessError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.model_create_multi
    def create(self, vals_list):
        self._check_hr_department_access_create(vals_list)
        return super().create(vals_list)

    def _check_hr_department_access_create(self, vals_list):
        """Mirror the department record rule using create vals.

        In Odoo 19, check_access("create") runs on hr.employee before the
        inherited hr.version is linked, so department_id is empty then.
        """
        if self.env.su:
            return
        department_ids = list(self.env["res.users"]._hr_authorized_department_ids())
        if not department_ids:
            return
        allowed = set(
            self.env["hr.department"].sudo().search([("id", "child_of", department_ids)]).ids
        )
        uid = self.env.uid
        for vals in vals_list:
            if vals.get("user_id") == uid:
                continue
            department_id = vals.get("department_id") or False
            if department_id not in allowed:
                raise AccessError(
                    self.env._(
                        "You can only create employees in your authorized departments."
                    )
                )
