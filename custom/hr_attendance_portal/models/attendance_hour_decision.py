# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class HrAttendanceHourDecision(models.Model):
    _name = "hr.attendance.hour.decision"
    _description = "Attendance Hour Decision"
    _order = "decided_at desc, id desc"

    attendance_id = fields.Many2one(
        "hr.attendance",
        string="Session",
        required=True,
        ondelete="cascade",
        index=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        related="attendance_id.employee_id",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="attendance_id.employee_id.company_id",
        store=True,
        index=True,
    )
    in_department_id = fields.Many2one(related="attendance_id.in_department_id", store=True)
    out_department_id = fields.Many2one(related="attendance_id.out_department_id", store=True)
    in_location_id = fields.Many2one(related="attendance_id.in_location_id", store=True)
    out_location_id = fields.Many2one(related="attendance_id.out_location_id", store=True)
    decision_type = fields.Selection(
        [
            ("deny_session", "Deny Session"),
            ("reduce_regular", "Reduce Hours"),
            ("restore_session", "Restore Session"),
        ],
        string="Decision",
        required=True,
        readonly=True,
    )
    regular_before = fields.Float(string="Hours Before", readonly=True, digits=(16, 4))
    regular_after = fields.Float(string="Hours After", readonly=True, digits=(16, 4))
    reason = fields.Text(string="Reason", required=True, readonly=True)
    user_id = fields.Many2one("res.users", string="Decided By", readonly=True)
    decided_at = fields.Datetime(
        string="Decided At",
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )
    role = fields.Selection(
        [("captain", "Captain"), ("hr", "HR")],
        string="Role",
        required=True,
        readonly=True,
    )

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._("Hour decisions cannot be edited."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(self.env._("Hour decisions cannot be deleted."))
        return super().unlink()
