# -*- coding: utf-8 -*-

from math import atan2, cos, radians, sin, sqrt

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrAttendanceLocation(models.Model):
    _name = "hr.attendance.location"
    _description = "Attendance Workplace"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    latitude = fields.Float(digits=(10, 7), required=True)
    longitude = fields.Float(digits=(10, 7), required=True)
    allowed_radius_meters = fields.Integer(
        string="Allowed Radius (m)",
        required=True,
        default=150,
        help="Employees must check in/out within this radius of the workplace.",
    )
    max_gps_accuracy_meters = fields.Integer(
        string="Max GPS Accuracy (m)",
        default=100,
        help="GPS readings less accurate than this are flagged for HR review.",
    )
    captain_ids = fields.Many2many(
        "res.users",
        "hr_attendance_location_captain_rel",
        "location_id",
        "user_id",
        string="Site Captains",
        domain="[('share', '=', False)]",
        help="These users can view employees assigned here and punches recorded at this workplace. They cannot edit them.",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        "hr_attendance_location_employee_rel",
        "location_id",
        "employee_id",
        string="Restricted Employees",
        help="If set, only these employees may use this workplace. Leave empty for all employees.",
    )
    linked_department_ids = fields.One2many(
        "hr.department",
        "attendance_location_id",
        string="Departments",
        help="Departments that check in and out at this workplace.",
    )
    department_ids = fields.Many2many(
        "hr.department",
        "hr_attendance_location_department_rel",
        "location_id",
        "department_id",
        string="Restricted Departments",
        help="If set, only employees in these departments may use this workplace.",
    )

    @api.constrains("allowed_radius_meters", "max_gps_accuracy_meters")
    def _check_positive_meters(self):
        for location in self:
            if location.allowed_radius_meters <= 0:
                raise ValidationError(self.env._("Allowed radius must be greater than zero."))
            if location.max_gps_accuracy_meters < 0:
                raise ValidationError(self.env._("Maximum GPS accuracy cannot be negative."))

    @api.constrains("latitude", "longitude")
    def _check_coordinates(self):
        for location in self:
            if not -90 <= location.latitude <= 90:
                raise ValidationError(self.env._("Latitude must be between -90 and 90."))
            if not -180 <= location.longitude <= 180:
                raise ValidationError(self.env._("Longitude must be between -180 and 180."))

    def _distance_meters(self, latitude, longitude):
        self.ensure_one()
        return self._haversine_meters(
            self.latitude, self.longitude, latitude, longitude
        )

    @staticmethod
    def _haversine_meters(lat1, lon1, lat2, lon2):
        radius = 6371000.0
        phi1, phi2 = radians(lat1), radians(lat2)
        d_phi = radians(lat2 - lat1)
        d_lambda = radians(lon2 - lon1)
        a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
        return 2 * radius * atan2(sqrt(a), sqrt(1 - a))

    def _resolved_workplace(self, department):
        """Workplace on this department, or the nearest parent that has one."""
        seen = set()
        current = department
        while current and current.id not in seen:
            seen.add(current.id)
            location = current.attendance_location_id
            if location and location.active:
                return location
            current = current.parent_id
        return self.browse()

    def _company_location_ok(self, employee, location):
        if not location:
            return False
        if employee.company_id and location.company_id and location.company_id != employee.company_id:
            return False
        return True

    def _match_result(self, location, department, distance, gps_accuracy):
        if gps_accuracy and location.max_gps_accuracy_meters and gps_accuracy > location.max_gps_accuracy_meters:
            return location, department, "gps_inaccurate", distance
        return location, department, False, distance

    def _match_for_employee(self, employee, latitude, longitude, gps_accuracy=None):
        """Return (location, department, reason_code, distance).

        Prefer the workplace of the employee's department. If the GPS is
        outside that circle, use another department whose workplace contains
        the point. If none do, the place is unknown.
        """
        Department = self.env["hr.department"].sudo()
        home = employee.department_id
        home_location = self._resolved_workplace(home) if home else self.browse()
        if self._company_location_ok(employee, home_location):
            distance = home_location._distance_meters(latitude, longitude)
            if distance <= home_location.allowed_radius_meters:
                return self._match_result(home_location, home, distance, gps_accuracy)

        company_ids = [employee.company_id.id, False] if employee.company_id else [False]
        candidates = Department.search([
            ("active", "=", True),
            ("attendance_location_id", "!=", False),
            ("attendance_location_id.active", "=", True),
            ("company_id", "in", company_ids),
        ])
        best = None
        for department in candidates:
            location = department.attendance_location_id
            if not self._company_location_ok(employee, location):
                continue
            if home_location and location == home_location:
                continue
            distance = location._distance_meters(latitude, longitude)
            if distance > location.allowed_radius_meters:
                continue
            rank = (distance, location.allowed_radius_meters, department.id)
            if best is None or rank < best[0]:
                best = (rank, location, department, distance)
        if best:
            _rank, location, department, distance = best
            return self._match_result(location, department, distance, gps_accuracy)
        return self.browse(), Department.browse(), "unknown_location", None
