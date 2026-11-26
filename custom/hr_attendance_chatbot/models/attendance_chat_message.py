# -*- coding: utf-8 -*-

from odoo import fields, models


class HrAttendanceChatMessage(models.Model):
    _name = "hr.attendance.chat.message"
    _description = "Attendance chatbot transcript line"
    _order = "id asc"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.uid,
    )
    role = fields.Selection(
        [
            ("user", "User"),
            ("assistant", "Assistant"),
        ],
        required=True,
    )
    body = fields.Text(required=True)
    proposal_id = fields.Many2one(
        "hr.attendance.chat.proposal",
        string="Linked proposal",
        ondelete="set null",
    )