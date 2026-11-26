# -*- coding: utf-8 -*-

import json

from odoo import fields, models


class HrAttendanceChatProposal(models.Model):
    _name = "hr.attendance.chat.proposal"
    _description = "Pending attendance write proposed in chat"
    _order = "id desc"

    user_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.uid,
    )
    attendance_id = fields.Many2one("hr.attendance", required=True, index=True, ondelete="cascade")
    method = fields.Selection(
        [
            ("action_reduce_regular", "Set recognized hours"),
            ("action_captain_overtime", "Captain overtime decision"),
        ],
        required=True,
    )
    argument_json = fields.Text(required=True)
    reason = fields.Text(required=True)
    summary_vi = fields.Text(
        string="Vietnamese summary",
        required=True,
        help="What the user sees before confirming.",
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("confirmed", "Confirmed"),
            ("dismissed", "Dismissed"),
            ("expired", "Expired"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    expires_at = fields.Datetime(required=True, index=True)
    confirmed_at = fields.Datetime(readonly=True)
    error_message = fields.Text(readonly=True)

    def get_arguments(self):
        self.ensure_one()
        return json.loads(self.argument_json or "{}")