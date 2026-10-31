# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


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
            self.hours, self.reason, rejected=False
        )
        return {"type": "ir.actions.act_window_close"}


class HrAttendanceOvertimeBulkWizard(models.TransientModel):
    _name = "hr.attendance.overtime.bulk.wizard"
    _description = "Attendance Bulk Overtime Decision Wizard"

    attendance_ids = fields.Many2many("hr.attendance", string="Selected Shifts", required=True)
    rejected = fields.Boolean(string="Reject Overtime")
    shift_count = fields.Integer(string="Shifts", compute="_compute_shift_count")
    reason = fields.Text(string="Reason", required=True)

    @api.depends("attendance_ids")
    def _compute_shift_count(self):
        for wizard in self:
            wizard.shift_count = len(wizard.attendance_ids)

    def action_apply(self):
        self.ensure_one()
        for attendance in self.attendance_ids:
            case = attendance.overtime_case_ids[:1]
            attendance.action_captain_overtime(case._cap_hours(), self.reason, rejected=False)
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


class HrAttendanceOvertimeHrBulkWizard(models.TransientModel):
    _name = "hr.attendance.overtime.hr.bulk.wizard"
    _description = "Attendance Bulk HR Overtime Review Wizard"

    attendance_ids = fields.Many2many("hr.attendance", string="Selected Shifts", required=True)
    shift_count = fields.Integer(string="Shifts", compute="_compute_shift_count")
    note = fields.Text(string="Review Note", required=True)

    @api.depends("attendance_ids")
    def _compute_shift_count(self):
        for wizard in self:
            wizard.shift_count = len(wizard.attendance_ids)

    def action_apply(self):
        self.ensure_one()
        for attendance in self.attendance_ids:
            case = attendance.overtime_case_ids[:1]
            attendance.action_hr_overtime(case.captain_hours, self.note, discrepancy=False)
        return {"type": "ir.actions.act_window_close"}


class HrAttendanceCheckoutWizard(models.TransientModel):
    _name = "hr.attendance.checkout.wizard"
    _description = "Attendance Checkout Confirmation Wizard"

    attendance_id = fields.Many2one("hr.attendance", required=True)
    check_out = fields.Datetime(string="Checkout Time", required=True)
    reason = fields.Text(string="Reason", required=True)

    def action_apply(self):
        self.ensure_one()
        self.attendance_id.action_confirm_checkout(self.check_out, self.reason)
        return {"type": "ir.actions.act_window_close"}


class HrAttendanceReduceBulkWizard(models.TransientModel):
    _name = "hr.attendance.reduce.bulk.wizard"
    _description = "Attendance Bulk Reduce Hours Wizard"

    attendance_ids = fields.Many2many("hr.attendance", string="Selected Shifts", required=True)
    shift_count = fields.Integer(string="Shifts", compute="_compute_shift_count")
    hours = fields.Float(string="Recognized Hours", digits=(16, 4), required=True)
    reason = fields.Text(string="Reason", required=True)

    @api.depends("attendance_ids")
    def _compute_shift_count(self):
        for wizard in self:
            wizard.shift_count = len(wizard.attendance_ids)

    def action_apply(self):
        self.ensure_one()
        if not self.attendance_ids:
            raise UserError(self.env._("No selected shift can have hours reduced."))
        for attendance in self.attendance_ids:
            attendance.action_reduce_regular(self.hours, self.reason)
        return {"type": "ir.actions.act_window_close"}


class HrAttendanceCorrectionBulkWizard(models.TransientModel):
    _name = "hr.attendance.correction.bulk.wizard"
    _description = "Attendance Bulk Time Correction Wizard"

    correction_type = fields.Selection(
        [("check_in", "Check-in"), ("check_out", "Check-out")],
        string="Boundary",
        required=True,
        default="check_out",
    )
    reason = fields.Text(string="Reason", required=True)
    line_ids = fields.One2many(
        "hr.attendance.correction.bulk.line",
        "wizard_id",
        string="Shifts",
    )

    @api.onchange("correction_type")
    def _onchange_correction_type(self):
        for line in self.line_ids:
            attendance = line.attendance_id
            if self.correction_type == "check_in":
                line.proposed_value = attendance.check_in
            else:
                line.proposed_value = attendance.check_out

    def action_apply(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._("No selected shift can be sent for a time correction."))
        for line in self.line_ids:
            line.attendance_id.action_request_correction(
                self.correction_type, line.proposed_value, self.reason
            )
        return {"type": "ir.actions.act_window_close"}


class HrAttendanceCorrectionBulkLine(models.TransientModel):
    _name = "hr.attendance.correction.bulk.line"
    _description = "Attendance Bulk Time Correction Line"

    wizard_id = fields.Many2one(
        "hr.attendance.correction.bulk.wizard",
        required=True,
        ondelete="cascade",
    )
    attendance_id = fields.Many2one("hr.attendance", required=True)
    employee_id = fields.Many2one(related="attendance_id.employee_id")
    check_in = fields.Datetime(related="attendance_id.check_in")
    check_out = fields.Datetime(related="attendance_id.check_out")
    proposed_value = fields.Datetime(string="Proposed Time", required=True)


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
