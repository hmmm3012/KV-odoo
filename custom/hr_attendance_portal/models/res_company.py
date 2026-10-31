# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    attendance_portal_session_minutes = fields.Integer(
        default=720,
        help="Personal-device attendance session lifetime in minutes.",
    )
    attendance_portal_kiosk_session_minutes = fields.Integer(
        default=2,
        help="Shared-kiosk attendance session lifetime in minutes. Sessions are revoked after each transaction.",
    )
    attendance_portal_pin_max_attempts = fields.Integer(default=5)
    attendance_portal_pin_window_minutes = fields.Integer(default=15)
    attendance_portal_ip_max_attempts = fields.Integer(default=30)
    attendance_portal_missing_gps_policy = fields.Selection(
        [("reject", "Reject"), ("needs_review", "Needs Review")],
        default="reject",
        required=True,
    )
    attendance_portal_gps_inaccurate_policy = fields.Selection(
        [("reject", "Reject"), ("needs_review", "Needs Review")],
        default="needs_review",
        required=True,
    )
    attendance_portal_outside_geofence_policy = fields.Selection(
        [("reject", "Reject"), ("needs_review", "Needs Review")],
        default="needs_review",
        required=True,
    )
    attendance_portal_no_location_policy = fields.Selection(
        [("reject", "Reject"), ("needs_review", "Needs Review")],
        default="needs_review",
        required=True,
    )
    attendance_portal_kiosk_require_gps = fields.Boolean(
        default=False,
        help="If enabled, kiosk check-in/out without GPS is handled by the missing-GPS policy.",
    )
    attendance_portal_missing_photo_policy = fields.Selection(
        [("reject", "Reject"), ("needs_review", "Needs Review")],
        default="reject",
        required=True,
        help="Personal devices capture a still for HR audit. Kiosk punches do not require a photo.",
    )
    attendance_portal_no_face_policy = fields.Selection(
        [("reject", "Reject"), ("needs_review", "Needs Review")],
        default="needs_review",
        required=True,
        help="Unused for live punches: quality failures always recapture. Kept for existing databases.",
    )
    attendance_portal_face_mismatch_policy = fields.Selection(
        [("reject", "Reject"), ("needs_review", "Needs Review")],
        default="needs_review",
        required=True,
        help="Mid cosine (about 30-45%) always needs HR verification and still records the punch. Below 30% always recaptures.",
    )
    attendance_standard_hours = fields.Float(
        default=8.0,
        help="Recognized regular hours per session. Time beyond this is an overtime candidate, not payroll overtime.",
    )
    attendance_overtime_cap_hours = fields.Float(
        default=4.0,
        help="Maximum overtime a captain may approve for one session.",
    )
    attendance_missing_checkout_hours = fields.Float(
        default=12.0,
        help="Flag a session that is still open after this many hours. No checkout is invented.",
    )
    attendance_google_maps_api_key = fields.Char(
        string="Google Maps API key",
        help="Maps JavaScript API key used to draw a workplace fence. Restrict the key to this Odoo site.",
    )
    attendance_portal_face_not_enrolled_policy = fields.Selection(
        [("reject", "Reject"), ("needs_review", "Needs Review")],
        default="needs_review",
        required=True,
        help="When the employee has no enrolled face vector. Needs Review still records the punch.",
    )
