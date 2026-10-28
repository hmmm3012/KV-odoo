# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    in_mode = fields.Selection(
        selection_add=[("personal_web", "Personal Web")],
        ondelete={"personal_web": "set default"},
    )
    out_mode = fields.Selection(
        selection_add=[("personal_web", "Personal Web")],
        ondelete={"personal_web": "set default"},
    )
    in_location_id = fields.Many2one(
        "hr.attendance.location",
        string="Check-in Workplace",
        readonly=True,
        ondelete="set null",
    )
    out_location_id = fields.Many2one(
        "hr.attendance.location",
        string="Check-out Workplace",
        readonly=True,
        ondelete="set null",
    )
    in_department_id = fields.Many2one(
        "hr.department",
        string="Check-in Department",
        readonly=True,
        ondelete="set null",
    )
    out_department_id = fields.Many2one(
        "hr.department",
        string="Check-out Department",
        readonly=True,
        ondelete="set null",
    )
    in_gps_accuracy = fields.Float(string="Check-in GPS Accuracy (m)", readonly=True)
    out_gps_accuracy = fields.Float(string="Check-out GPS Accuracy (m)", readonly=True)
    in_face_image = fields.Binary(
        string="Check-in Photo",
        attachment=True,
        readonly=True,
    )
    in_face_detected = fields.Boolean(string="Check-in Face Detected", readonly=True)
    out_face_image = fields.Binary(
        string="Check-out Photo",
        attachment=True,
        readonly=True,
    )
    out_face_detected = fields.Boolean(string="Check-out Face Detected", readonly=True)
    portal_review_status = fields.Selection(
        [
            ("not_required", "Not Required"),
            ("pending", "Pending"),
            ("reviewed", "Reviewed"),
        ],
        default="not_required",
        index=True,
        string="Portal Review",
    )
    portal_event_ids = fields.One2many(
        "hr.attendance.event",
        "attendance_id",
        string="Portal Events",
    )
    portal_event_count = fields.Integer(compute="_compute_portal_event_count")

    def _compute_portal_event_count(self):
        counts = {}
        if self.ids:
            grouped = self.env["hr.attendance.event"].sudo()._read_group(
                [("attendance_id", "in", self.ids)],
                ["attendance_id"],
                ["__count"],
            )
            counts = {attendance.id: count for attendance, count in grouped}
        for attendance in self:
            attendance.portal_event_count = counts.get(attendance.id, 0)

    session_state = fields.Selection(
        [
            ("active", "Active"),
            ("pending_review", "Pending Review"),
            ("validated", "Validated"),
            ("denied", "Denied"),
            ("modification_pending", "Modification Pending"),
            ("corrected", "Corrected"),
            ("closed", "Closed"),
        ],
        string="Session Status",
        default="active",
        index=True,
        copy=False,
    )
    exception_code = fields.Selection(
        [
            ("none", "None"),
            ("missing_checkout", "Missing Checkout"),
            ("excessive_duration", "Excessive Duration"),
        ],
        string="Exception",
        default="none",
        index=True,
        copy=False,
    )
    raw_elapsed_hours = fields.Float(
        string="Raw Elapsed",
        digits=(16, 4),
        readonly=True,
        copy=False,
    )
    standard_hours = fields.Float(
        string="Standard Hours",
        digits=(16, 4),
        readonly=True,
        copy=False,
        help="Snapshot of the company standard hours when the session was classified.",
    )
    recognized_regular_hours = fields.Float(
        string="Recognized Hours",
        digits=(16, 4),
        readonly=True,
        copy=False,
    )
    effective_check_in = fields.Datetime(
        string="Effective Check-in",
        readonly=True,
        copy=False,
        help="Used for hour calculation only after HR approves a boundary correction.",
    )
    effective_check_out = fields.Datetime(
        string="Effective Check-out",
        readonly=True,
        copy=False,
        help="Used for hour calculation only after HR approves a boundary correction.",
    )
    overtime_candidate_hours = fields.Float(
        string="Overtime Candidate",
        digits=(16, 4),
        readonly=True,
        copy=False,
    )
    overtime_state = fields.Selection(
        [
            ("not_required", "Not Required"),
            ("pending_captain", "Pending Captain"),
            ("pending_hr_review", "Pending HR Review"),
            ("captain_rejected", "Captain Rejected"),
            ("hr_reviewed", "HR Reviewed"),
            ("hr_discrepancy", "HR Discrepancy"),
            ("closed", "Closed"),
        ],
        string="Overtime Review",
        default="not_required",
        index=True,
        copy=False,
    )
    payroll_regular_hours = fields.Float(
        string="Payroll Regular Hours",
        digits=(16, 4),
        readonly=True,
        copy=False,
    )
    payroll_overtime_hours = fields.Float(
        string="Payroll Overtime Hours",
        digits=(16, 4),
        readonly=True,
        copy=False,
    )
    resource_calendar_id = fields.Many2one(
        "resource.calendar",
        related="employee_id.resource_calendar_id",
        string="Work Schedule",
        readonly=True,
    )
    hour_decision_ids = fields.One2many(
        "hr.attendance.hour.decision",
        "attendance_id",
        string="Hour Decisions",
    )
    overtime_case_ids = fields.One2many(
        "hr.attendance.overtime.case",
        "attendance_id",
        string="Overtime Cases",
    )
    correction_ids = fields.One2many(
        "hr.attendance.correction",
        "attendance_id",
        string="Time Corrections",
    )
    work_status = fields.Selection(
        [("at_work", "At Work"), ("finished", "Finished")],
        string="Work Status",
        compute="_compute_work_status",
    )
    can_decide_session = fields.Boolean(compute="_compute_session_buttons")
    can_review_overtime = fields.Boolean(compute="_compute_session_buttons")
    can_hr_review = fields.Boolean(compute="_compute_session_buttons")

    _DERIVED_SESSION_FIELDS = {
        "session_state",
        "exception_code",
        "raw_elapsed_hours",
        "standard_hours",
        "recognized_regular_hours",
        "effective_check_in",
        "effective_check_out",
        "overtime_candidate_hours",
        "overtime_state",
        "payroll_regular_hours",
        "payroll_overtime_hours",
    }

    @api.depends("check_out")
    def _compute_work_status(self):
        for attendance in self:
            attendance.work_status = "finished" if attendance.check_out else "at_work"

    @api.depends("session_state", "overtime_candidate_hours", "overtime_state")
    def _compute_session_buttons(self):
        user = self.env.user
        is_captain = user.has_group("hr_attendance_portal.group_hr_attendance_site_captain")
        is_hr = user.has_group("hr_attendance.group_hr_attendance_officer")
        for attendance in self:
            open_session = attendance.session_state != "closed"
            attendance.can_decide_session = open_session and (is_captain or is_hr)
            attendance.can_review_overtime = (
                open_session
                and attendance.session_state != "denied"
                and attendance.overtime_state in ("pending_captain", "pending_hr_review")
                and (is_captain or is_hr)
            )
            attendance.can_hr_review = (
                is_hr
                and open_session
                and attendance.overtime_state in ("pending_hr_review", "hr_discrepancy", "captain_rejected")
            )

    def action_open_portal_events(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Attendance Events"),
            "res_model": "hr.attendance.event",
            "view_mode": "list,form",
            "domain": [("attendance_id", "=", self.id)],
            "context": {"default_attendance_id": self.id, "default_employee_id": self.employee_id.id},
        }

    @api.model
    def _session_elapsed(self, start, end):
        if not start or not end or end < start:
            return 0.0
        return (end - start).total_seconds() / 3600.0

    @api.model
    def _round_seconds_to_half_hour(self, total_seconds):
        """Snap a duration to a half hour.

        A remainder of 15 minutes or more rounds up to the next half hour.
        A smaller remainder floors to the previous half hour. The result is
        only a whole hour or a half hour (12:00, 12:30, 13:00, ...).
        """
        if not total_seconds or total_seconds <= 0:
            return 0
        total_seconds = int(total_seconds)
        half_hour = 30 * 60
        remainder = total_seconds % half_hour
        if remainder >= 15 * 60:
            return total_seconds + (half_hour - remainder)
        return total_seconds - remainder

    @api.model
    def _round_elapsed_hours(self, start, end):
        if not start or not end or end < start:
            return 0.0
        seconds = self._round_seconds_to_half_hour((end - start).total_seconds())
        return seconds / 3600.0

    @api.model
    def _round_worked_hours(self, hours):
        if not hours or hours <= 0:
            return 0.0
        seconds = self._round_seconds_to_half_hour(round(hours * 3600.0))
        return seconds / 3600.0

    def _compute_worked_hours(self):
        super()._compute_worked_hours()
        for attendance in self:
            if attendance.worked_hours:
                attendance.worked_hours = attendance._round_worked_hours(attendance.worked_hours)

    def _session_bounds(self):
        self.ensure_one()
        start = self.effective_check_in or self.check_in
        end = self.effective_check_out or self.check_out
        return start, end

    def _session_duration(self):
        self.ensure_one()
        start, end = self._session_bounds()
        return self._round_elapsed_hours(start, end)

    def _max_regular_hours(self):
        """Regular hours cannot exceed the standard day or the elapsed time."""
        self.ensure_one()
        standard = self.standard_hours or 0.0
        duration = self._session_duration()
        if not standard:
            return duration
        return min(standard, duration)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._classify_session()
        return records

    def write(self, vals):
        protected = {"check_in", "check_out"} & set(vals)
        if protected and not self.env.context.get("attendance_original_punch"):
            captain_checkout = (
                self.env.context.get("attendance_captain_checkout")
                and protected == {"check_out"}
                and all(not attendance.check_out for attendance in self)
            )
            if not captain_checkout:
                raise UserError(self.env._(
                    "Original check-in and check-out times cannot be changed."
                ))
        if (
            not self.env.context.get("attendance_session_apply")
            and self._DERIVED_SESSION_FIELDS & set(vals)
        ):
            raise UserError(self.env._(
                "Recognized hours are changed only through a session decision."
            ))
        res = super().write(vals)
        if (
            ("check_out" in vals or "check_in" in vals)
            and not self.env.context.get("attendance_session_apply")
        ):
            self._classify_session()
        return res

    def _apply_session_vals(self, vals):
        self.with_context(attendance_session_apply=True).sudo().write(vals)

    def _classify_session(self, force=False):
        """Set recognized hours from the original or HR-approved bounds.

        A captain decision is left in place unless ``force`` is set by an
        approved boundary correction.
        """
        Case = self.env["hr.attendance.overtime.case"].sudo()
        now = fields.Datetime.now()
        for attendance in self:
            if attendance.session_state in ("closed", "denied"):
                continue
            company = attendance.employee_id.company_id or self.env.company
            raw = self._session_elapsed(attendance.check_in, attendance.check_out)
            _start, end = attendance._session_bounds()
            duration = attendance._session_duration()
            has_end = bool(end)
            standard_default = company.attendance_standard_hours or 8.0
            standard = attendance.standard_hours or (standard_default if has_end else 0.0)
            vals = {"raw_elapsed_hours": raw}
            if has_end and not attendance.standard_hours:
                vals["standard_hours"] = standard_default
                standard = standard_default
            locked = bool(attendance.hour_decision_ids) and not force
            if not has_end:
                if not locked and attendance.session_state != "modification_pending":
                    open_hours = self._session_elapsed(attendance.check_in, now)
                    threshold = company.attendance_missing_checkout_hours or 12.0
                    missing = bool(attendance.check_in and open_hours > threshold)
                    vals.update({
                        "session_state": "pending_review" if missing else "active",
                        "exception_code": "missing_checkout" if missing else "none",
                        "recognized_regular_hours": 0.0,
                        "payroll_regular_hours": 0.0,
                        "payroll_overtime_hours": 0.0,
                        "overtime_candidate_hours": 0.0,
                        "overtime_state": "not_required",
                    })
                attendance._apply_session_vals(vals)
                continue
            if locked or attendance.session_state == "modification_pending":
                attendance._apply_session_vals(vals)
                continue
            if float_compare(duration, standard, precision_digits=4) <= 0:
                corrected = bool(attendance.effective_check_in or attendance.effective_check_out)
                vals.update({
                    "session_state": "corrected" if corrected else "validated",
                    "exception_code": "none",
                    "recognized_regular_hours": duration,
                    "payroll_regular_hours": duration,
                    "overtime_candidate_hours": 0.0,
                    "payroll_overtime_hours": 0.0,
                    "overtime_state": "not_required",
                })
                attendance._apply_session_vals(vals)
                case = attendance.overtime_case_ids[:1]
                if case and case.state not in ("hr_reviewed", "closed"):
                    case.sudo().write({
                        "state": "not_required",
                        "payroll_hours": 0.0,
                    })
                continue
            candidate = duration - standard
            case = attendance.overtime_case_ids[:1]
            captain_decided = bool(case) and case.state not in ("pending_captain", "not_required")
            if captain_decided:
                corrected = bool(attendance.effective_check_in or attendance.effective_check_out)
                vals.update({
                    "session_state": "corrected" if corrected else "validated",
                    "exception_code": "none",
                    "recognized_regular_hours": standard,
                    "payroll_regular_hours": standard,
                    "overtime_candidate_hours": candidate,
                    "overtime_state": case.state,
                })
                attendance._apply_session_vals(vals)
                continue
            vals.update({
                "session_state": "pending_review",
                "exception_code": "excessive_duration",
                "recognized_regular_hours": standard,
                "payroll_regular_hours": standard,
                "overtime_candidate_hours": candidate,
                "payroll_overtime_hours": 0.0,
                "overtime_state": "pending_captain",
            })
            attendance._apply_session_vals(vals)
            Case._ensure_case(attendance, candidate)
        return True

    @api.model
    def _release_reviewed_overtime_sessions(self):
        """Drop overtime shifts from the captain queue once a captain has decided.

        Older approvals stored the overtime decision but left the session in
        Pending Review, so the shift stayed on Sessions To Review.
        """
        sessions = self.sudo().search([
            ("session_state", "=", "pending_review"),
            ("exception_code", "=", "excessive_duration"),
            ("overtime_state", "not in", ["not_required", "pending_captain"]),
        ])
        for attendance in sessions:
            corrected = bool(attendance.effective_check_in or attendance.effective_check_out)
            attendance._apply_session_vals({
                "session_state": "corrected" if corrected else "validated",
                "exception_code": "none",
            })
        return True

    @api.model
    def _cron_flag_missing_checkout(self):
        open_sessions = self.sudo().search([
            ("check_out", "=", False),
            ("effective_check_out", "=", False),
            ("session_state", "in", ["active", "pending_review"]),
        ])
        open_sessions._classify_session()

    def _ensure_session_open(self):
        self.ensure_one()
        if self.session_state == "closed":
            raise UserError(self.env._("A closed session cannot be changed."))

    def _session_actor_role(self):
        user = self.env.user
        if user.has_group("hr_attendance.group_hr_attendance_officer"):
            return "hr"
        if user.has_group("hr_attendance_portal.group_hr_attendance_site_captain"):
            return "captain"
        raise AccessError(self.env._("You cannot change recognized hours."))

    def _check_session_visible(self):
        self.ensure_one()
        self.check_access("read")

    def _require_reason(self, reason):
        reason = (reason or "").strip()
        if not reason:
            raise UserError(self.env._("A reason is required."))
        return reason

    def action_deny_session(self, reason=None):
        self.ensure_one()
        self._check_session_visible()
        self._ensure_session_open()
        role = self._session_actor_role()
        reason = (reason or "").strip() or self.env._("Deny Session")
        before = self.recognized_regular_hours
        self.env["hr.attendance.hour.decision"].sudo().create({
            "attendance_id": self.id,
            "decision_type": "deny_session",
            "regular_before": before,
            "regular_after": 0.0,
            "reason": reason,
            "user_id": self.env.uid,
            "role": role,
        })
        self._apply_session_vals({
            "session_state": "denied",
            "recognized_regular_hours": 0.0,
            "payroll_regular_hours": 0.0,
            "payroll_overtime_hours": 0.0,
        })
        case = self.overtime_case_ids[:1]
        if case and case.state not in ("closed",):
            case.sudo().action_record_captain(
                hours=0.0,
                reason=reason,
                rejected=True,
                from_session_deny=True,
                actor_id=self.env.uid,
            )
        return True

    def action_reduce_regular(self, hours, reason):
        self.ensure_one()
        self._check_session_visible()
        self._ensure_session_open()
        if self.session_state == "denied":
            raise UserError(self.env._("A denied session has no hours to reduce."))
        role = self._session_actor_role()
        reason = self._require_reason(reason)
        before = self.recognized_regular_hours
        if float_compare(hours, 0.0, precision_digits=4) < 0:
            raise UserError(self.env._("Recognized hours cannot be negative."))
        if float_compare(hours, before, precision_digits=4) > 0:
            raise UserError(self.env._("Recognized hours cannot be increased."))
        self.env["hr.attendance.hour.decision"].sudo().create({
            "attendance_id": self.id,
            "decision_type": "reduce_regular",
            "regular_before": before,
            "regular_after": hours,
            "reason": reason,
            "user_id": self.env.uid,
            "role": role,
        })
        state = self.session_state
        if state == "active":
            state = "validated"
        self._apply_session_vals({
            "recognized_regular_hours": hours,
            "payroll_regular_hours": hours,
            "session_state": state,
        })
        return True

    def action_restore_session(self, hours, reason):
        self.ensure_one()
        self._check_session_visible()
        self._ensure_session_open()
        if self._session_actor_role() != "hr":
            raise AccessError(self.env._("Only HR can restore a denied session."))
        reason = self._require_reason(reason)
        cap = self._max_regular_hours()
        if float_compare(hours, 0.0, precision_digits=4) < 0 or float_compare(hours, cap, precision_digits=4) > 0:
            raise UserError(self.env._(
                "Restored hours cannot exceed the standard hours or the elapsed time."
            ))
        before = self.recognized_regular_hours
        self.env["hr.attendance.hour.decision"].sudo().create({
            "attendance_id": self.id,
            "decision_type": "restore_session",
            "regular_before": before,
            "regular_after": hours,
            "reason": reason,
            "user_id": self.env.uid,
            "role": "hr",
        })
        corrected = bool(self.effective_check_in or self.effective_check_out)
        self._apply_session_vals({
            "session_state": "corrected" if corrected else "validated",
            "recognized_regular_hours": hours,
            "payroll_regular_hours": hours,
        })
        return True

    def action_captain_overtime(self, hours, reason, rejected=False):
        self.ensure_one()
        self._check_session_visible()
        self._ensure_session_open()
        if self.session_state == "denied":
            raise UserError(self.env._("A denied session has no overtime to review."))
        self._session_actor_role()
        reason = self._require_reason(reason)
        case = self.overtime_case_ids[:1]
        if not case:
            raise UserError(self.env._("This session has no overtime to review."))
        case.sudo().action_record_captain(
            hours=hours, reason=reason, rejected=rejected, actor_id=self.env.uid
        )
        return True

    def action_hr_overtime(self, hours, note, discrepancy=False):
        self.ensure_one()
        self._check_session_visible()
        self._ensure_session_open()
        if self._session_actor_role() != "hr":
            raise AccessError(self.env._("Only HR can review overtime."))
        note = self._require_reason(note)
        case = self.overtime_case_ids[:1]
        if not case:
            raise UserError(self.env._("This session has no overtime to review."))
        case.sudo().action_record_hr(
            hours=hours, note=note, discrepancy=discrepancy, actor_id=self.env.uid
        )
        return True

    def action_request_correction(self, correction_type, proposed, reason, attachment=False):
        self.ensure_one()
        self._check_session_visible()
        self._ensure_session_open()
        self._session_actor_role()
        return self.env["hr.attendance.correction"].sudo().submit_for(
            self,
            correction_type,
            proposed,
            reason,
            attachment=attachment,
            requester_id=self.env.uid,
        )

    def action_close_session(self):
        self.ensure_one()
        self._check_session_visible()
        if self._session_actor_role() != "hr":
            raise AccessError(self.env._("Only HR can close a session."))
        if self.session_state == "closed":
            return True
        self._apply_session_vals({"session_state": "closed"})
        case = self.overtime_case_ids[:1]
        if case:
            case.sudo().write({"state": "closed"})
            self._apply_session_vals({"overtime_state": "closed"})
        return True

    def action_confirm_checkout(self, check_out, reason):
        """Close an open shift with the checkout time a captain confirms.

        The original check-in stays unchanged. This is only for a shift that
        has no checkout yet, so the employee can start a new shift afterwards.
        """
        self.ensure_one()
        self._check_session_visible()
        self._ensure_session_open()
        if self.check_out:
            raise UserError(self.env._("This shift already has a checkout."))
        if not check_out:
            raise UserError(self.env._("A checkout time is required."))
        if check_out <= self.check_in:
            raise UserError(self.env._("Checkout must be after check-in."))
        if check_out > fields.Datetime.now():
            raise UserError(self.env._("Checkout cannot be in the future."))
        role = self._session_actor_role()
        reason = self._require_reason(reason)
        actor_id = self.env.uid
        before = self.recognized_regular_hours
        self.with_context(attendance_captain_checkout=True).sudo().write({
            "check_out": check_out,
            "out_mode": "manual",
        })
        self.env["hr.attendance.hour.decision"].sudo().create({
            "attendance_id": self.id,
            "decision_type": "confirm_checkout",
            "regular_before": before,
            "regular_after": self.recognized_regular_hours,
            "reason": reason,
            "user_id": actor_id,
            "role": role,
        })
        return True

    def action_open_confirm_checkout_wizard(self):
        self.ensure_one()
        self._check_session_visible()
        self._ensure_session_open()
        if self.check_out:
            raise UserError(self.env._("This shift already has a checkout."))
        company = self.employee_id.company_id or self.env.company
        standard = company.attendance_standard_hours or 8.0
        suggested = self.check_in + timedelta(hours=standard)
        now = fields.Datetime.now()
        if suggested > now:
            suggested = now
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Confirm Checkout"),
            "res_model": "hr.attendance.checkout.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_attendance_id": self.id,
                "default_check_out": suggested,
            },
        }

    def action_open_deny_wizard(self):
        return self._open_hour_wizard("deny_session")

    def action_open_reduce_wizard(self):
        return self._open_hour_wizard("reduce_regular")

    def action_open_restore_wizard(self):
        return self._open_hour_wizard("restore_session")

    def _open_hour_wizard(self, decision_type):
        self.ensure_one()
        self._check_session_visible()
        self._ensure_session_open()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Session Decision"),
            "res_model": "hr.attendance.hour.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_attendance_id": self.id,
                "default_decision_type": decision_type,
                "default_hours": self.recognized_regular_hours,
            },
        }

    def _overtime_waiting_for_captain(self):
        return self.filtered(lambda attendance: (
            attendance.session_state not in ("closed", "denied")
            and attendance.overtime_state == "pending_captain"
            and attendance.overtime_case_ids
        ))

    def action_open_bulk_overtime_wizard(self):
        """Open one decision for every selected shift that is waiting on the captain."""
        waiting = self._overtime_waiting_for_captain()
        if not waiting:
            raise UserError(self.env._(
                "No selected shift is waiting for overtime approval."
            ))
        for attendance in waiting:
            attendance._check_session_visible()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Approve Selected Overtime"),
            "res_model": "hr.attendance.overtime.bulk.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_attendance_ids": [(6, 0, waiting.ids)],
                "default_rejected": False,
            },
        }

    def action_open_overtime_wizard(self):
        self.ensure_one()
        self._check_session_visible()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Overtime Decision"),
            "res_model": "hr.attendance.overtime.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_attendance_id": self.id,
                "default_hours": self.overtime_candidate_hours,
            },
        }

    def action_open_hr_overtime_wizard(self):
        self.ensure_one()
        self._check_session_visible()
        case = self.overtime_case_ids[:1]
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("HR Overtime Review"),
            "res_model": "hr.attendance.overtime.hr.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_attendance_id": self.id,
                "default_hours": case.captain_hours if case else 0.0,
            },
        }

    def _corrections_waiting(self):
        pending = self.env["hr.attendance.correction"].sudo().search([
            ("attendance_id", "in", self.ids),
            ("state", "=", "pending"),
        ]).mapped("attendance_id")
        return self.filtered(lambda attendance: (
            attendance.session_state != "closed"
            and attendance not in pending
        ))

    def action_open_bulk_correction_wizard(self):
        """Ask HR to correct several selected shifts in one request."""
        waiting = self._corrections_waiting()
        if not waiting:
            raise UserError(self.env._(
                "No selected shift can be sent for a time correction."
            ))
        for attendance in waiting:
            attendance._check_session_visible()
        lines = [
            (0, 0, {
                "attendance_id": attendance.id,
                "proposed_value": attendance.check_out or attendance.check_in,
            })
            for attendance in waiting
        ]
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Request Time Correction"),
            "res_model": "hr.attendance.correction.bulk.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_line_ids": lines,
                "default_correction_type": "check_out",
            },
        }

    def action_open_correction_wizard(self):
        self.ensure_one()
        self._check_session_visible()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Request Time Correction"),
            "res_model": "hr.attendance.correction.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_attendance_id": self.id},
        }
