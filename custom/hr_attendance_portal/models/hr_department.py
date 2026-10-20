# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .attendance_location import HrAttendanceLocation


class HrDepartment(models.Model):
    _inherit = "hr.department"

    attendance_location_id = fields.Many2one(
        "hr.attendance.location",
        string="Workplace",
        ondelete="restrict",
        help="GPS workplace where employees of this department check in and out. "
        "A child department uses its own workplace, or the nearest parent workplace when this is empty.",
    )
    attendance_latitude = fields.Float(
        string="Attendance Latitude",
        digits=(10, 7),
        help="If set with longitude, this department is an attendance site. Departments with the same coordinates are treated as one place; the employee's own department is shown when it is in that group.",
    )
    attendance_longitude = fields.Float(
        string="Attendance Longitude",
        digits=(10, 7),
    )
    attendance_radius_meters = fields.Integer(
        string="Attendance Radius (m)",
        default=150,
        help="Employees must check in/out within this radius of the department.",
    )
    attendance_max_gps_accuracy_meters = fields.Integer(
        string="Max GPS Accuracy (m)",
        default=100,
        help="GPS readings less accurate than this are flagged for HR review.",
    )
    attendance_is_geofenced = fields.Boolean(
        compute="_compute_attendance_is_geofenced",
        string="Attendance Site",
    )

    @api.depends("attendance_latitude", "attendance_longitude")
    def _compute_attendance_is_geofenced(self):
        for department in self:
            department.attendance_is_geofenced = bool(
                department.attendance_latitude and department.attendance_longitude
            )

    @api.constrains("attendance_radius_meters", "attendance_max_gps_accuracy_meters")
    def _check_attendance_meters(self):
        for department in self:
            if department.attendance_radius_meters < 0:
                raise ValidationError(self.env._("Attendance radius cannot be negative."))
            if department.attendance_max_gps_accuracy_meters < 0:
                raise ValidationError(self.env._("Maximum GPS accuracy cannot be negative."))

    @api.constrains("attendance_latitude", "attendance_longitude")
    def _check_attendance_coordinates(self):
        for department in self:
            if department.attendance_latitude and not -90 <= department.attendance_latitude <= 90:
                raise ValidationError(self.env._("Latitude must be between -90 and 90."))
            if department.attendance_longitude and not -180 <= department.attendance_longitude <= 180:
                raise ValidationError(self.env._("Longitude must be between -180 and 180."))

    def _attendance_distance_meters(self, latitude, longitude):
        self.ensure_one()
        return HrAttendanceLocation._haversine_meters(
            self.attendance_latitude, self.attendance_longitude, latitude, longitude
        )

    SAME_PLACE_METERS = 25

    def _match_attendance_geofence(self, employee, latitude, longitude, gps_accuracy=None):
        """Return (department, reason_code, distance) for the closest geofenced place.

        Departments that share coordinates (same building) are one place. The
        label prefers the employee's own department, then a common parent site.
        """
        candidates = self.filtered(lambda dept: dept.attendance_is_geofenced)
        if not candidates:
            return self.browse(), "no_location_configured", None

        distances = {
            department.id: department._attendance_distance_meters(latitude, longitude)
            for department in candidates
        }
        closest_distance = min(distances.values())
        closest = candidates.filtered(lambda dept: distances[dept.id] <= closest_distance + 0.5)
        anchor = closest[:1]
        tied = candidates.filtered(
            lambda dept: dept._attendance_distance_meters(
                anchor.attendance_latitude, anchor.attendance_longitude
            ) <= self.SAME_PLACE_METERS
        )
        best = tied._pick_attendance_department(employee)
        best_distance = distances.get(best.id, closest_distance)
        radius = max(tied.mapped("attendance_radius_meters") or [0])
        if radius <= 0 or closest_distance > radius:
            return best, "outside_geofence", closest_distance
        accuracy_limit = min(
            tied.mapped("attendance_max_gps_accuracy_meters") or [0]
        )
        if gps_accuracy and accuracy_limit and gps_accuracy > accuracy_limit:
            return best, "gps_inaccurate", closest_distance
        return best, False, closest_distance

    def _pick_attendance_department(self, employee):
        """Choose which department name represents a shared GPS place."""
        if not self:
            return self.browse()
        if len(self) == 1:
            return self
        emp_dept = employee.department_id if employee else self.env["hr.department"].browse()
        if emp_dept in self:
            return emp_dept
        ancestor = emp_dept.parent_id
        while ancestor:
            if ancestor in self:
                return ancestor
            ancestor = ancestor.parent_id
        parents = self.mapped("parent_id").filtered(lambda dept: dept)
        if len(parents) == 1:
            return parents
        with_children = self.filtered(lambda dept: dept.child_ids)
        if len(with_children) == 1:
            return with_children
        return self.sorted(lambda dept: (dept.name or "").casefold())[:1]
