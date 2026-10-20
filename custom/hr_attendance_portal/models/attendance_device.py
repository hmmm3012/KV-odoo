# -*- coding: utf-8 -*-

from odoo import fields, models


class HrAttendanceDevice(models.Model):
    _name = "hr.attendance.device"
    _description = "Attendance Kiosk Device"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    device_identifier = fields.Char(
        string="Device Identifier",
        required=True,
        index=True,
        help="Stable identifier sent by the shared kiosk. Do not put secrets in frontend code.",
    )
    location_id = fields.Many2one("hr.attendance.location", string="Workplace", ondelete="restrict")
    last_seen_at = fields.Datetime(string="Last Seen", readonly=True)
    revoked_at = fields.Datetime(string="Revoked At", readonly=True)
    notes = fields.Char()

    _sql_constraints = [
        (
            "device_identifier_uniq",
            "unique(device_identifier)",
            "Device identifier must be unique.",
        ),
    ]

    def action_revoke(self):
        self.write({"revoked_at": fields.Datetime.now(), "active": False})

    def action_reactivate(self):
        self.write({"revoked_at": False, "active": True})

    def _is_usable(self):
        self.ensure_one()
        return bool(self.active and not self.revoked_at)
