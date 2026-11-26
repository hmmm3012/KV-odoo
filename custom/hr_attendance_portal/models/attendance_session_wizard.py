# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class HrAttendanceHourWizard(models.TransientModel):
    _name = "hr.attendance.hour.wizard"
    _description = "Attendance Hour Decision Wizard"

    attendance_id = fields.Many2one("hr.attendance", required=True)
    decision_type = fields.Selection(
        [
            ("deny_session", "Deny Session"),
            ("reduce_regular", "Adjust Work Hours"),
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
            self.hours, self.reason, rejected=bool(self.rejected)
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
            attendance.action_captain_overtime(
                case._cap_hours(),
                self.reason,
                rejected=bool(self.rejected),
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
        """Deprecated path: close forgotten checkout via time correction."""
        self.ensure_one()
        self.attendance_id.action_request_correction(
            "check_out", self.check_out, self.reason
        )
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
                line.proposed_value = (
                    attendance.check_out
                    or attendance.effective_check_out
                    or attendance._suggested_checkout()
                )

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
    _description = "Adjust Work Hours Wizard"

    attendance_id = fields.Many2one("hr.attendance", required=True)
    adjustment_mode = fields.Selection(
        [
            ("punch", "Edit check-in / check-out"),
            ("recognized", "Enter recognized total"),
        ],
        string="Adjustment",
        required=True,
        default="punch",
    )
    proposed_check_in = fields.Datetime(string="Check-in")
    proposed_check_out = fields.Datetime(string="Check-out")
    recognized_hours = fields.Float(string="Recognized Hours", digits=(16, 4))
    elapsed_hours = fields.Float(string="Shift Duration", digits=(16, 4))
    can_set_recognized_hours = fields.Boolean()
    reason = fields.Text(string="Reason")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        attendance = self.env["hr.attendance"].browse(
            res.get("attendance_id") or self.env.context.get("default_attendance_id")
        )
        if not attendance:
            return res
        res.setdefault(
            "proposed_check_in",
            attendance.effective_check_in or attendance.check_in,
        )
        res.setdefault(
            "proposed_check_out",
            attendance.effective_check_out
            or attendance.check_out
            or attendance._suggested_checkout(),
        )
        res.setdefault("recognized_hours", attendance._current_recognized_total())
        res["elapsed_hours"] = (
            attendance._session_duration() if attendance._session_bounds()[1] else 0.0
        )
        res["can_set_recognized_hours"] = attendance._can_set_recognized_hours()
        mode = res.get("adjustment_mode") or self.env.context.get(
            "default_adjustment_mode", "punch"
        )
        if not res.get("can_set_recognized_hours"):
            mode = "punch"
        res["adjustment_mode"] = mode
        return res

    def _reload(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Adjust Work Hours"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context),
        }

    def action_nudge_recognized(self):
        """Shift recognized hours by the button delta and stay in the dialog."""
        self.ensure_one()
        if not self.can_set_recognized_hours:
            raise UserError(self.env._(
                "Recognized hours cannot be changed on this session."
            ))
        delta = float(self.env.context.get("nudge_hours") or 0.0)
        hours = (self.recognized_hours or 0.0) + delta
        if float_compare(hours, 0.0, precision_digits=4) < 0:
            hours = 0.0
        elapsed = self.elapsed_hours or 0.0
        if elapsed and float_compare(hours, elapsed, precision_digits=4) > 0:
            hours = elapsed
        self.write({
            "adjustment_mode": "recognized",
            "recognized_hours": hours,
        })
        return self._reload()

    def _apply_punch_corrections(self):
        attendance = self.attendance_id
        current_in = attendance.effective_check_in or attendance.check_in
        current_out = attendance.effective_check_out or attendance.check_out
        new_in = self.proposed_check_in
        new_out = self.proposed_check_out
        if new_in and new_out and new_out <= new_in:
            raise UserError(self.env._(
                "The proposed end cannot be earlier than the start."
            ))
        change_in = bool(new_in) and new_in != current_in
        change_out = bool(new_out) and new_out != current_out
        if not change_in and not change_out:
            raise UserError(self.env._(
                "Change check-in, check-out, or recognized hours."
            ))
        reason = self.reason
        apply_out_first = (
            change_in
            and change_out
            and current_out
            and new_in >= current_out
        )
        if apply_out_first:
            attendance.action_request_correction("check_out", new_out, reason)
            attendance.action_request_correction("check_in", new_in, reason)
            return
        if change_in:
            attendance.action_request_correction("check_in", new_in, reason)
        if change_out:
            attendance.action_request_correction("check_out", new_out, reason)

    def action_apply(self):
        self.ensure_one()
        if self.adjustment_mode == "recognized":
            if not self.can_set_recognized_hours:
                raise UserError(self.env._(
                    "Recognized hours cannot be changed on this session."
                ))
            self.attendance_id.action_reduce_regular(self.recognized_hours, self.reason)
        else:
            self._apply_punch_corrections()
        return {"type": "ir.actions.act_window_close"}
