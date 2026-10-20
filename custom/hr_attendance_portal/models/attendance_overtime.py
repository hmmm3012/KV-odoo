# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class HrAttendanceOvertimeCase(models.Model):
    _name = "hr.attendance.overtime.case"
    _description = "Attendance Overtime Review"
    _order = "id desc"

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
    candidate_hours = fields.Float(string="Candidate Hours", readonly=True, digits=(16, 4))
    captain_hours = fields.Float(string="Captain Hours", readonly=True, digits=(16, 4))
    hr_hours = fields.Float(string="HR Hours", readonly=True, digits=(16, 4))
    payroll_hours = fields.Float(string="Payroll Hours", readonly=True, digits=(16, 4))
    state = fields.Selection(
        [
            ("not_required", "Not Required"),
            ("pending_captain", "Pending Captain"),
            ("pending_hr_review", "Pending HR Review"),
            ("captain_rejected", "Captain Rejected"),
            ("hr_reviewed", "HR Reviewed"),
            ("hr_discrepancy", "HR Discrepancy"),
            ("closed", "Closed"),
        ],
        string="Status",
        default="pending_captain",
        required=True,
        index=True,
    )
    captain_user_id = fields.Many2one("res.users", string="Captain", readonly=True)
    captain_at = fields.Datetime(string="Captain Decision At", readonly=True)
    captain_reason = fields.Text(string="Captain Reason", readonly=True)
    hr_user_id = fields.Many2one("res.users", string="HR Reviewer", readonly=True)
    hr_at = fields.Datetime(string="HR Review At", readonly=True)
    hr_note = fields.Text(string="HR Note", readonly=True)
    decision_ids = fields.One2many(
        "hr.attendance.overtime.decision",
        "case_id",
        string="Decisions",
    )

    _sql_constraints = [
        (
            "attendance_uniq",
            "unique(attendance_id)",
            "Each session has one overtime case.",
        ),
    ]

    @api.model
    def _ensure_case(self, attendance, candidate):
        case = self.search([("attendance_id", "=", attendance.id)], limit=1)
        if not case:
            return self.create({
                "attendance_id": attendance.id,
                "candidate_hours": candidate,
                "state": "pending_captain",
                "payroll_hours": 0.0,
            })
        if case.state == "closed":
            return case
        case.write({
            "candidate_hours": candidate,
            "captain_hours": 0.0,
            "hr_hours": 0.0,
            "payroll_hours": 0.0,
            "state": "pending_captain",
        })
        return case

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._("Overtime review is changed only through a decision."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(self.env._("Overtime review cannot be deleted."))
        return super().unlink()

    def _cap_hours(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        policy_cap = company.attendance_overtime_cap_hours or 0.0
        cap = self.candidate_hours or 0.0
        if policy_cap:
            cap = min(cap, policy_cap)
        return cap

    def _log(self, decision_type, before, after, reason, actor_id):
        self.ensure_one()
        self.env["hr.attendance.overtime.decision"].sudo().create({
            "case_id": self.id,
            "decision_type": decision_type,
            "hours_before": before,
            "hours_after": after,
            "reason": reason,
            "user_id": actor_id,
        })

    def action_record_captain(self, hours, reason, rejected=False, from_session_deny=False, actor_id=None):
        self.ensure_one()
        if self.state in ("hr_reviewed", "closed"):
            raise UserError(self.env._("Overtime has already been reviewed by HR."))
        if self.attendance_id.session_state == "closed":
            raise UserError(self.env._("A closed session cannot be changed."))
        if rejected:
            hours = 0.0
            decision_type = "captain_reject"
        else:
            cap = self._cap_hours()
            if float_compare(hours, 0.0, precision_digits=4) < 0 or float_compare(hours, cap, precision_digits=4) > 0:
                raise UserError(self.env._(
                    "Approved overtime cannot exceed the candidate hours or the policy cap."
                ))
            decision_type = "captain_approve"
        actor_id = actor_id or self.env.uid
        before = self.captain_hours
        self._log(decision_type, before, hours, reason, actor_id)
        state = "captain_rejected" if from_session_deny else "pending_hr_review"
        self.write({
            "captain_hours": hours,
            "captain_user_id": actor_id,
            "captain_at": fields.Datetime.now(),
            "captain_reason": reason,
            "payroll_hours": 0.0,
            "hr_hours": 0.0,
            "state": state,
        })
        self.attendance_id._apply_session_vals({
            "overtime_state": state,
            "payroll_overtime_hours": 0.0,
        })

    def action_record_hr(self, hours, note, discrepancy=False, actor_id=None):
        self.ensure_one()
        if self.state not in ("pending_hr_review", "hr_discrepancy", "captain_rejected"):
            raise UserError(self.env._("HR reviews overtime after the captain decision."))
        if self.attendance_id.session_state == "closed":
            raise UserError(self.env._("A closed session cannot be changed."))
        ceiling = self.captain_hours or 0.0
        if float_compare(hours, 0.0, precision_digits=4) < 0 or float_compare(hours, ceiling, precision_digits=4) > 0:
            raise UserError(self.env._(
                "HR cannot approve more overtime than the captain approved."
            ))
        decision_type = "hr_discrepancy" if discrepancy else "hr_review"
        actor_id = actor_id or self.env.uid
        before = self.hr_hours
        self._log(decision_type, before, hours, note, actor_id)
        state = "hr_discrepancy" if discrepancy else "hr_reviewed"
        payroll = 0.0 if discrepancy else hours
        self.write({
            "hr_hours": hours,
            "hr_user_id": actor_id,
            "hr_at": fields.Datetime.now(),
            "hr_note": note,
            "payroll_hours": payroll,
            "state": state,
        })
        self.attendance_id._apply_session_vals({
            "overtime_state": state,
            "payroll_overtime_hours": payroll,
        })


class HrAttendanceOvertimeDecision(models.Model):
    _name = "hr.attendance.overtime.decision"
    _description = "Attendance Overtime Decision"
    _order = "decided_at desc, id desc"

    case_id = fields.Many2one(
        "hr.attendance.overtime.case",
        string="Overtime Case",
        required=True,
        ondelete="cascade",
        index=True,
        readonly=True,
    )
    attendance_id = fields.Many2one(
        related="case_id.attendance_id",
        store=True,
        index=True,
    )
    employee_id = fields.Many2one(related="case_id.employee_id", store=True, index=True)
    company_id = fields.Many2one(related="case_id.company_id", store=True, index=True)
    in_department_id = fields.Many2one(related="case_id.in_department_id", store=True)
    out_department_id = fields.Many2one(related="case_id.out_department_id", store=True)
    in_location_id = fields.Many2one(related="case_id.in_location_id", store=True)
    out_location_id = fields.Many2one(related="case_id.out_location_id", store=True)
    decision_type = fields.Selection(
        [
            ("captain_approve", "Captain Approve"),
            ("captain_reject", "Captain Reject"),
            ("hr_review", "HR Review"),
            ("hr_discrepancy", "HR Discrepancy"),
        ],
        string="Decision",
        required=True,
        readonly=True,
    )
    hours_before = fields.Float(string="Hours Before", readonly=True, digits=(16, 4))
    hours_after = fields.Float(string="Hours After", readonly=True, digits=(16, 4))
    reason = fields.Text(string="Reason", required=True, readonly=True)
    user_id = fields.Many2one("res.users", string="Decided By", readonly=True)
    decided_at = fields.Datetime(
        string="Decided At",
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._("Overtime decisions cannot be edited."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(self.env._("Overtime decisions cannot be deleted."))
        return super().unlink()
