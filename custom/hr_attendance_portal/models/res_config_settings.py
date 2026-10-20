# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    attendance_portal_session_minutes = fields.Integer(
        related="company_id.attendance_portal_session_minutes",
        readonly=False,
    )
    attendance_portal_kiosk_session_minutes = fields.Integer(
        related="company_id.attendance_portal_kiosk_session_minutes",
        readonly=False,
    )
    attendance_portal_pin_max_attempts = fields.Integer(
        related="company_id.attendance_portal_pin_max_attempts",
        readonly=False,
    )
    attendance_portal_pin_window_minutes = fields.Integer(
        related="company_id.attendance_portal_pin_window_minutes",
        readonly=False,
    )
    attendance_portal_ip_max_attempts = fields.Integer(
        related="company_id.attendance_portal_ip_max_attempts",
        readonly=False,
    )
    attendance_portal_missing_gps_policy = fields.Selection(
        related="company_id.attendance_portal_missing_gps_policy",
        readonly=False,
    )
    attendance_portal_gps_inaccurate_policy = fields.Selection(
        related="company_id.attendance_portal_gps_inaccurate_policy",
        readonly=False,
    )
    attendance_portal_outside_geofence_policy = fields.Selection(
        related="company_id.attendance_portal_outside_geofence_policy",
        readonly=False,
    )
    attendance_portal_no_location_policy = fields.Selection(
        related="company_id.attendance_portal_no_location_policy",
        readonly=False,
    )
    attendance_portal_kiosk_require_gps = fields.Boolean(
        related="company_id.attendance_portal_kiosk_require_gps",
        readonly=False,
    )
    attendance_portal_missing_photo_policy = fields.Selection(
        related="company_id.attendance_portal_missing_photo_policy",
        readonly=False,
    )
    attendance_portal_no_face_policy = fields.Selection(
        related="company_id.attendance_portal_no_face_policy",
        readonly=False,
    )
    attendance_portal_face_mismatch_policy = fields.Selection(
        related="company_id.attendance_portal_face_mismatch_policy",
        readonly=False,
    )
    attendance_standard_hours = fields.Float(
        related="company_id.attendance_standard_hours",
        readonly=False,
    )
    attendance_overtime_cap_hours = fields.Float(
        related="company_id.attendance_overtime_cap_hours",
        readonly=False,
    )
    attendance_missing_checkout_hours = fields.Float(
        related="company_id.attendance_missing_checkout_hours",
        readonly=False,
    )
    attendance_portal_face_not_enrolled_policy = fields.Selection(
        related="company_id.attendance_portal_face_not_enrolled_policy",
        readonly=False,
    )
