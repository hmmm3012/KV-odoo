# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrAttendanceEvent(models.Model):
    _name = "hr.attendance.event"
    _description = "Attendance Audit Event"
    _order = "server_time desc, id desc"

    employee_id = fields.Many2one("hr.employee", string="Employee", index=True, ondelete="set null")
    attendance_id = fields.Many2one("hr.attendance", string="Attendance", index=True, ondelete="set null")
    company_id = fields.Many2one(
        "res.company",
        related="employee_id.company_id",
        store=True,
        index=True,
    )
    event_type = fields.Selection(
        [("check_in", "Check In"), ("check_out", "Check Out")],
        string="Type",
        required=True,
        index=True,
    )
    result = fields.Selection(
        [
            ("success", "Success"),
            ("rejected", "Rejected"),
            ("needs_review", "Needs Review"),
        ],
        string="Result",
        required=True,
        index=True,
    )
    source = fields.Selection(
        [("personal_web", "Personal Web"), ("kiosk", "Kiosk")],
        string="Source",
        required=True,
        default="personal_web",
        index=True,
    )
    request_id = fields.Char(string="Request ID", index=True)
    server_time = fields.Datetime(string="Time", required=True, default=fields.Datetime.now, index=True)
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    gps_accuracy = fields.Float(string="GPS Accuracy (m)")
    distance_meters = fields.Float(string="Distance (m)")
    face_image = fields.Binary(
        string="Punch Photo",
        attachment=True,
        readonly=True,
    )
    face_count = fields.Integer(string="Faces Detected", readonly=True)
    face_cosine = fields.Float(string="Face Cosine", digits=(16, 6), readonly=True)
    location_id = fields.Many2one("hr.attendance.location", string="Workplace", ondelete="set null")
    department_id = fields.Many2one("hr.department", string="Department / Site", ondelete="set null")
    device_id = fields.Many2one("hr.attendance.device", string="Device", ondelete="set null")
    ip_address = fields.Char(string="IP Address")
    failure_reason_code = fields.Selection(
        [
            ("invalid_credentials", "Invalid credentials"),
            ("too_many_attempts", "Too many attempts"),
            ("inactive_employee", "Inactive employee"),
            ("pin_not_set", "PIN not set"),
            ("not_eligible", "Not eligible"),
            ("invalid_session", "Invalid session"),
            ("missing_gps", "Missing GPS"),
            ("missing_photo", "Missing photo"),
            ("no_face", "No face in photo"),
            ("multiple_faces", "Multiple faces in photo"),
            ("face_too_small", "Face too small"),
            ("face_tilted", "Face tilted"),
            ("face_turned", "Face turned"),
            ("face_mismatch", "Face mismatch"),
            ("face_low_match", "Face match too low"),
            ("face_not_enrolled", "Face not enrolled"),
            ("face_check_unavailable", "Face check unavailable"),
            ("gps_inaccurate", "GPS inaccurate"),
            ("outside_geofence", "Outside geofence"),
            ("no_location_configured", "No workplace configured"),
            ("unknown_location", "Unknown location"),
            ("device_revoked", "Device revoked"),
            ("already_checked_in", "Already checked in"),
            ("not_checked_in", "Not checked in"),
            ("duplicate_request", "Duplicate request"),
            ("invalid_event_type", "Invalid event type"),
        ],
        string="Reason",
        index=True,
    )
    review_status = fields.Selection(
        [
            ("not_required", "Not Required"),
            ("pending", "Pending"),
            ("reviewed", "Reviewed"),
        ],
        string="Review",
        default="not_required",
        required=True,
        index=True,
    )
    reviewed_by = fields.Many2one("res.users", string="Reviewed By", readonly=True)
    reviewed_at = fields.Datetime(string="Reviewed At", readonly=True)
    review_note = fields.Text(string="Note")

    _sql_constraints = [
        (
            "request_id_uniq",
            "unique(request_id)",
            "Duplicate attendance request.",
        ),
    ]

    @api.model
    def _log(self, values):
        values = dict(values)
        values.setdefault("server_time", fields.Datetime.now())
        if values.get("result") == "needs_review":
            values.setdefault("review_status", "pending")
        elif values.get("result") == "success":
            values.setdefault("review_status", "not_required")
        else:
            values.setdefault("review_status", "not_required")
        return self.create(values)

    def unlink(self):
        if not self.env.is_superuser():
            raise UserError(self.env._("Attendance events cannot be deleted."))
        return super().unlink()

    def action_mark_reviewed(self):
        self.write({
            "review_status": "reviewed",
            "reviewed_by": self.env.uid,
            "reviewed_at": fields.Datetime.now(),
        })
        attendances = self.mapped("attendance_id").filtered("id")
        if attendances:
            attendances.write({"portal_review_status": "reviewed"})
