# -*- coding: utf-8 -*-

from odoo import fields, models


class HrAttendanceHourWizard(models.TransientModel):
    _name = "hr.attendance.hour.wizard"
    _description = "Attendance Hour Decision Wizard"

    attendance_id = fields.Many2one("hr.attendance", required=True)
    decision_type = fields.Selection(
        [
            ("deny_session", "Deny Session"),
            ("reduce_regular", "Reduce Hours"),
            ("restore_session", "Restore Session"),
        ],
        required=True,
    )
    hours = fields.Float(string="Recognized Hours", digits=(16, 4))
    reason = fields.Text(string="Reason", required=True)

    def action_apply(self):
        self.ensure_one()
        attendance = self.attendance_id
        if self.decision_type == "deny_session":
            attendance.action_deny_session(self.reason)
        elif self.decision_type == "reduce_regular":
            attendance.action_reduce_regular(self.hours, self.reason)
        else:
            attendance.action_restore_session(self.hours, self.reason)
        return {"type": "ir.actions.act_window_close"}


class HrAttendanceOvertimeWizard(models.TransientModel):
    _name = "hr.attendance.overtime.wizard"
    _description = "Attendance Overtime Decision Wizard"

    attendance_id = fields.Many2one("hr.attendance", required=True)
    rejected = fields.Boolean(string="Reject Overtime")
    hours = fields.Float(string="Approved Overtime", digits=(16, 4))
    reason = fields.Text(string="Reason", required=True)

    def action_apply(self):
        self.ensure_one()
        self.attendance_id.action_captain_overtime(
            self.hours, self.reason, rejected=self.rejected
        )
        return {"type": "ir.actions.act_window_close"}


class HrAttendanceOvertimeHrWizard(models.TransientModel):
    _name = "hr.attendance.overtime.hr.wizard"
    _description = "Attendance HR Overtime Review Wizard"

    attendance_id = fields.Many2one("hr.attendance", required=True)
    discrepancy = fields.Boolean(string="Discrepancy")
    hours = fields.Float(string="Payroll Overtime", digits=(16, 4))
    note = fields.Text(string="Review Note", required=True)

    def action_apply(self):
        self.ensure_one()
        self.attendance_id.action_hr_overtime(
            self.hours, self.note, discrepancy=self.discrepancy
        )
        return {"type": "ir.actions.act_window_close"}


class HrAttendanceCorrectionWizard(models.TransientModel):
    _name = "hr.attendance.correction.wizard"
    _description = "Attendance Time Correction Wizard"

    attendance_id = fields.Many2one("hr.attendance", required=True)
    correction_type = fields.Selection(
        [("check_in", "Check-in"), ("check_out", "Check-out")],
        string="Boundary",
        required=True,
        default="check_out",
    )
    proposed_value = fields.Datetime(string="Proposed Time", required=True)
    reason = fields.Text(string="Reason", required=True)

    def action_apply(self):
        self.ensure_one()
        self.attendance_id.action_request_correction(
            self.correction_type, self.proposed_value, self.reason
        )
        return {"type": "ir.actions.act_window_close"}
