# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .attendance_location import HrAttendanceLocation

STRUCTURE_FIELDS = frozenset((
    "structure_qlbx", "structure_cskh", "structure_day", "structure_night",
    "structure_note", "off_max_day", "off_max_night",
))


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

    structure_qlbx = fields.Integer("Cơ cấu QLBX", tracking=True)
    structure_cskh = fields.Integer("Cơ cấu CSKH", tracking=True)
    structure_day = fields.Integer("Cơ cấu ca ngày", tracking=True)
    structure_night = fields.Integer("Cơ cấu ca đêm", tracking=True)
    structure_total = fields.Integer(
        "Tổng cơ cấu",
        compute="_compute_structure_total",
        store=True,
    )
    structure_note = fields.Char("Ghi chú cơ cấu", tracking=True)

    actual_qlbx = fields.Integer("Thực tế QLBX", compute="_compute_structure_actual")
    actual_cskh = fields.Integer("Thực tế CSKH", compute="_compute_structure_actual")
    actual_day = fields.Integer("Thực tế ca ngày", compute="_compute_structure_actual")
    actual_night = fields.Integer("Thực tế ca đêm", compute="_compute_structure_actual")
    actual_unassigned = fields.Integer(
        "Chưa xếp ca",
        compute="_compute_structure_actual",
        help="Nhân viên không thuộc nhóm QLBX/CSKH và chưa chọn \"Ca làm việc\" trong hồ sơ.",
    )
    actual_total = fields.Integer("Tổng thực tế", compute="_compute_structure_actual")
    gap_qlbx = fields.Integer("Thừa/thiếu QLBX", compute="_compute_structure_actual")
    gap_cskh = fields.Integer("Thừa/thiếu CSKH", compute="_compute_structure_actual")
    gap_day = fields.Integer("Thừa/thiếu ca ngày", compute="_compute_structure_actual")
    gap_night = fields.Integer("Thừa/thiếu ca đêm", compute="_compute_structure_actual")
    gap_total = fields.Integer("Thừa/thiếu tổng", compute="_compute_structure_actual")

    off_max_day = fields.Integer(
        "OFF tối đa/ngày - ca ngày",
        tracking=True,
        help="Số nhân viên ca ngày được OFF cùng một ngày. 0 = không giới hạn.",
    )
    off_max_night = fields.Integer(
        "OFF tối đa/ngày - ca đêm",
        tracking=True,
        help="Số nhân viên ca đêm được OFF cùng một ngày. 0 = không giới hạn.",
    )
    off_count = fields.Integer(
        "Lịch OFF",
        compute="_compute_off_count",
        groups="hr.group_hr_user,hr_attendance.group_hr_attendance_officer,"
        "hr_attendance_portal.group_hr_attendance_site_captain",
    )

    @api.depends("structure_qlbx", "structure_cskh", "structure_day", "structure_night")
    def _compute_structure_total(self):
        for department in self:
            department.structure_total = (
                department.structure_qlbx
                + department.structure_cskh
                + department.structure_day
                + department.structure_night
            )

    @api.depends(
        "member_ids.job_id.structure_role",
        "member_ids.employee_properties",
        "structure_qlbx",
        "structure_cskh",
        "structure_day",
        "structure_night",
    )
    def _compute_structure_actual(self):
        Timesheet = self.env["hr.attendance.timesheet.wizard"]
        for department in self:
            counts = dict.fromkeys(("qlbx", "cskh", "day", "night", "unassigned"), 0)
            for employee in department.sudo().member_ids:
                bucket = (
                    employee.job_id.structure_role
                    or Timesheet._employee_work_shift_value(employee)
                    or "unassigned"
                )
                counts[bucket] += 1
            department.actual_qlbx = counts["qlbx"]
            department.actual_cskh = counts["cskh"]
            department.actual_day = counts["day"]
            department.actual_night = counts["night"]
            department.actual_unassigned = counts["unassigned"]
            department.actual_total = sum(counts.values())
            department.gap_qlbx = counts["qlbx"] - department.structure_qlbx
            department.gap_cskh = counts["cskh"] - department.structure_cskh
            department.gap_day = counts["day"] - department.structure_day
            department.gap_night = counts["night"] - department.structure_night
            department.gap_total = department.actual_total - department.structure_total

    def _compute_off_count(self):
        groups = self.env["hr.department.off"]._read_group(
            [("department_id", "in", self.ids), ("date", ">=", fields.Date.context_today(self))],
            ["department_id"],
            ["__count"],
        )
        counts = {department.id: count for department, count in groups}
        for department in self:
            department.off_count = counts.get(department.id, 0)

    def write(self, vals):
        # Stock HR lets every internal user write departments; keep the plan with HR.
        if STRUCTURE_FIELDS.intersection(vals) and not self.env.su and not (
            self.env.user.has_group("hr.group_hr_user")
            or self.env.user.has_group("hr_attendance.group_hr_attendance_officer")
        ):
            raise AccessError(self.env._("Chỉ nhân sự được sửa cơ cấu và số OFF tối đa của phòng ban."))
        return super().write(vals)

    def action_open_off_calendar(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "hr_attendance_portal.action_hr_department_off_calendar"
        )
        action["context"] = {"default_department_id": self.id}
        return action

    def action_open_off_schedule(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "hr_attendance_portal.action_hr_department_off"
        )
        action["domain"] = [("department_id", "=", self.id)]
        action["context"] = {"default_department_id": self.id}
        return action

    @api.depends("attendance_latitude", "attendance_longitude")
    def _compute_attendance_is_geofenced(self):
        for department in self:
            department.attendance_is_geofenced = bool(
                department.attendance_latitude and department.attendance_longitude
            )

    @api.constrains(
        "structure_qlbx", "structure_cskh", "structure_day", "structure_night",
        "off_max_day", "off_max_night",
    )
    def _check_structure_numbers(self):
        for department in self:
            if min(
                department.structure_qlbx, department.structure_cskh,
                department.structure_day, department.structure_night,
                department.off_max_day, department.off_max_night,
            ) < 0:
                raise ValidationError(self.env._("Số cơ cấu và số OFF tối đa không được âm."))

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
