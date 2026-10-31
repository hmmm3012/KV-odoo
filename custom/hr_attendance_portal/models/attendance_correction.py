# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class HrAttendanceCorrection(models.Model):
    _name = "hr.attendance.correction"
    _description = "Attendance Time Correction"
    _order = "requested_at desc, id desc"

    attendance_id = fields.Many2one(
        "hr.attendance",
        string="Session",
        required=True,
        ondelete="cascade",
        index=True,
        readonly=True,
    )
    event_id = fields.Many2one(
        "hr.attendance.event",
        string="Source Event",
        ondelete="set null",
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
    correction_type = fields.Selection(
        [("check_in", "Check-in"), ("check_out", "Check-out")],
        string="Boundary",
        required=True,
        readonly=True,
    )
    original_value = fields.Datetime(string="Original Value", readonly=True)
    proposed_value = fields.Datetime(string="Proposed Value", required=True, readonly=True)
    applied_value = fields.Datetime(string="Applied Value", readonly=True)
    reason = fields.Text(string="Reason", required=True, readonly=True)
    requester_id = fields.Many2one("res.users", string="Requested By", readonly=True)
    requested_at = fields.Datetime(string="Requested At", readonly=True)
    attachment = fields.Binary(string="Evidence", attachment=True)
    state = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        string="Status",
        default="pending",
        required=True,
        index=True,
    )
    previous_session_state = fields.Char(readonly=True)
    decider_id = fields.Many2one("res.users", string="Decided By", readonly=True)
    decided_at = fields.Datetime(string="Decided At", readonly=True)
    decision_reason = fields.Text(string="Decision Reason", readonly=True)

    def write(self, vals):
        locked = {
            "attendance_id",
            "original_value",
            "proposed_value",
            "reason",
            "requester_id",
            "correction_type",
        }
        if locked & set(vals) and not self.env.su:
            raise UserError(self.env._("A correction request cannot be rewritten."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(self.env._("A correction request cannot be deleted."))
        return super().unlink()

    def _effective_field_name(self):
        self.ensure_one()
        return (
            "effective_check_in"
            if self.correction_type == "check_in"
            else "effective_check_out"
        )

    def _apply_to_attendance(self, decider_id, decision_reason):
        """Apply the proposed boundary and reclassify the session."""
        for correction in self:
            if correction.attendance_id.session_state == "closed":
                raise UserError(self.env._("A closed session cannot be changed."))
            correction.write({
                "state": "approved",
                "decider_id": decider_id,
                "decided_at": fields.Datetime.now(),
                "decision_reason": decision_reason,
                "applied_value": correction.proposed_value,
            })
            attendance = correction.attendance_id
            attendance._apply_session_vals({
                correction._effective_field_name(): correction.proposed_value,
            })
            if attendance.session_state != "denied":
                attendance._classify_session(force=True)

    @api.model
    def submit_for(self, attendance, correction_type, proposed, reason, attachment=False, requester_id=None):
        reason = (reason or "").strip()
        if not reason:
            raise UserError(self.env._("A reason is required."))
        if correction_type not in ("check_in", "check_out"):
            raise UserError(self.env._("Choose a check-in or check-out correction."))
        if not proposed:
            raise UserError(self.env._("A proposed time is required."))
        if attendance.session_state == "closed":
            raise UserError(self.env._("A closed session cannot be changed."))
        original = attendance.check_in if correction_type == "check_in" else attendance.check_out
        start = proposed if correction_type == "check_in" else (attendance.effective_check_in or attendance.check_in)
        end = proposed if correction_type == "check_out" else (attendance.effective_check_out or attendance.check_out)
        if start and end and end < start:
            raise UserError(self.env._("The proposed end cannot be earlier than the start."))
        actor_id = requester_id or self.env.uid
        correction = self.create({
            "attendance_id": attendance.id,
            "correction_type": correction_type,
            "original_value": original,
            "proposed_value": proposed,
            "reason": reason,
            "requester_id": actor_id,
            "requested_at": fields.Datetime.now(),
            "attachment": attachment,
            "previous_session_state": attendance.session_state,
        })
        # Captain (or officer) correction is final: apply immediately.
        correction.sudo()._apply_to_attendance(actor_id, reason)
        return correction

    @api.model
    def _finalize_pending_corrections(self):
        """Apply correction requests that were still waiting for HR."""
        pending = self.search([("state", "=", "pending")])
        for correction in pending:
            if correction.attendance_id.session_state == "closed":
                continue
            actor_id = correction.requester_id.id or self.env.uid
            reason = correction.reason or self.env._("Captain decision")
            correction.sudo()._apply_to_attendance(actor_id, reason)
        return True

    def _check_hr_decider(self):
        self.ensure_one()
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_officer"):
            raise AccessError(self.env._("Only HR can decide a time correction."))
        if self.state != "pending":
            raise UserError(self.env._("This correction has already been decided."))
        if self.attendance_id.session_state == "closed":
            raise UserError(self.env._("A closed session cannot be changed."))

    def action_approve_button(self):
        self.action_approve(self.decision_reason)
        return True

    def action_reject_button(self):
        self.action_reject(self.decision_reason)
        return True

    def action_approve(self, decision_reason):
        decision_reason = (decision_reason or "").strip()
        if not decision_reason:
            raise UserError(self.env._("A reason is required."))
        for correction in self:
            correction._check_hr_decider()
            correction._apply_to_attendance(self.env.uid, decision_reason)
        return True

    def action_reject(self, decision_reason):
        decision_reason = (decision_reason or "").strip()
        if not decision_reason:
            raise UserError(self.env._("A reason is required."))
        for correction in self:
            correction._check_hr_decider()
            correction.write({
                "state": "rejected",
                "decider_id": self.env.uid,
                "decided_at": fields.Datetime.now(),
                "decision_reason": decision_reason,
            })
            previous = correction.previous_session_state or "active"
            if previous == "modification_pending":
                previous = "pending_review"
            correction.attendance_id._apply_session_vals({"session_state": previous})
        return True
