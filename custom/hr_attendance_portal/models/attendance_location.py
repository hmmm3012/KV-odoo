# -*- coding: utf-8 -*-

import json
from math import atan2, cos, hypot, pi, radians, sin, sqrt

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
        help="Used when this workplace has no polygon zone. Employees must check in/out within this radius of the center.",
    )
    zone_ids = fields.One2many(
        "hr.attendance.location.zone",
        "location_id",
        string="Polygon zones",
        copy=True,
    )
    vertex_ids = fields.One2many(
        "hr.attendance.location.vertex",
        "location_id",
        string="Fence points",
    )
    vertex_editor = fields.Text(
        string="Workplace fence",
        compute="_compute_vertex_editor",
        inverse="_inverse_vertex_editor",
        help="One or more polygon zones. Each zone needs at least 4 points.",
    )
    fence_mode = fields.Selection(
        [("circle", "Circle"), ("polygon", "Polygon")],
        string="Fence",
        compute="_compute_fence_mode",
        store=True,
    )
    zone_count = fields.Integer(compute="_compute_zone_count", string="Zones")
    google_maps_api_key = fields.Char(
        related="company_id.attendance_google_maps_api_key",
        string="Google Maps API key",
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

    @api.depends(
        "zone_ids",
        "zone_ids.name",
        "zone_ids.sequence",
        "zone_ids.vertex_ids",
        "zone_ids.vertex_ids.sequence",
        "zone_ids.vertex_ids.latitude",
        "zone_ids.vertex_ids.longitude",
    )
    def _compute_vertex_editor(self):
        for location in self:
            zones = []
            for zone in location.zone_ids.sorted(key=lambda item: (item.sequence, item.id)):
                vertices = zone.vertex_ids.sorted(key=lambda vertex: (vertex.sequence, vertex.id))
                zones.append({
                    "name": zone.name or "",
                    "points": [
                        {"latitude": vertex.latitude, "longitude": vertex.longitude}
                        for vertex in vertices
                    ],
                })
            location.vertex_editor = json.dumps(zones)

    def _inverse_vertex_editor(self):
        for location in self:
            location._set_fence_zones(location._parse_vertex_editor(location.vertex_editor))

    @api.depends("zone_ids", "zone_ids.vertex_ids")
    def _compute_fence_mode(self):
        for location in self:
            location.fence_mode = "polygon" if location._uses_polygon() else "circle"

    @api.depends("zone_ids")
    def _compute_zone_count(self):
        for location in self:
            location.zone_count = len(location.zone_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_centroid()
        return records

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get("skip_fence_centroid"):
            self.filtered(lambda location: location._uses_polygon())._sync_centroid()
        return result

    @api.model
    def _migrate_vertices_to_zones(self):
        """Move legacy flat vertices into Zone 1 for each workplace."""
        Vertex = self.env["hr.attendance.location.vertex"].sudo()
        Zone = self.env["hr.attendance.location.zone"].sudo()
        orphans = Vertex.search([("zone_id", "=", False), ("location_id", "!=", False)])
        for location in orphans.mapped("location_id"):
            location_orphans = orphans.filtered(lambda vertex: vertex.location_id == location)
            if not location_orphans:
                continue
            zone = Zone.create({
                "location_id": location.id,
                "name": self.env._("Zone 1"),
                "sequence": 1,
            })
            location_orphans.write({"zone_id": zone.id})

    def _parse_vertex_editor(self, raw):
        try:
            payload = json.loads(raw or "[]")
        except json.JSONDecodeError as error:
            raise ValidationError(self.env._("Workplace fence points are not valid.")) from error
        if not isinstance(payload, list):
            raise ValidationError(self.env._("Workplace fence points are not valid."))
        if not payload:
            return []
        if payload and isinstance(payload[0], dict) and "latitude" in payload[0]:
            return [{"name": self.env._("Zone 1"), "points": payload}]
        zones = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict) or "points" not in item:
                raise ValidationError(self.env._("Workplace fence points are not valid."))
            zones.append({
                "name": (item.get("name") or self.env._("Zone %(n)s", n=index)).strip(),
                "points": item.get("points") or [],
            })
        return zones

    def _sync_centroid(self):
        for location in self:
            vertices = location.vertex_ids
            if len(vertices) < 4:
                continue
            latitude = sum(vertices.mapped("latitude")) / len(vertices)
            longitude = sum(vertices.mapped("longitude")) / len(vertices)
            if abs(location.latitude - latitude) < 1e-8 and abs(location.longitude - longitude) < 1e-8:
                continue
            location.with_context(skip_fence_centroid=True).write({
                "latitude": latitude,
                "longitude": longitude,
            })

    def _polygon_zones(self):
        self.ensure_one()
        return self.zone_ids.filtered(lambda zone: len(zone.vertex_ids) >= 4)

    def _uses_polygon(self):
        self.ensure_one()
        return bool(self._polygon_zones())

    def _set_fence_points(self, points):
        """Replace all zones with a single polygon."""
        self.ensure_one()
        return self._set_fence_zones([{
            "name": self.env._("Zone 1"),
            "points": [{"latitude": lat, "longitude": lon} for lat, lon in points],
        }])

    def _set_fence_zones(self, zones):
        """Replace all polygon zones. Each item is {name, points:[{latitude,longitude}| (lat,lon)]}."""
        self.ensure_one()
        commands = [(5, 0, 0)]
        for index, zone in enumerate(zones or [], start=1):
            raw_points = zone.get("points") or []
            pairs = []
            for point in raw_points:
                if isinstance(point, dict):
                    pairs.append((point.get("latitude"), point.get("longitude")))
                else:
                    pairs.append(point)
            points = self._normalize_fence_points(pairs)
            if not points:
                continue
            vertex_commands = []
            for sequence, (latitude, longitude) in enumerate(points, start=1):
                vertex_commands.append((0, 0, {
                    "sequence": sequence,
                    "latitude": latitude,
                    "longitude": longitude,
                }))
            commands.append((0, 0, {
                "name": (zone.get("name") or self.env._("Zone %(n)s", n=index)).strip() or self.env._("Zone %(n)s", n=index),
                "sequence": index,
                "vertex_ids": vertex_commands,
            }))
        self.zone_ids = commands
        return self

    def _add_fence_zone(self, points, name=False):
        """Append one polygon zone without clearing existing zones."""
        self.ensure_one()
        points = self._normalize_fence_points(points)
        sequence = max(self.zone_ids.mapped("sequence") or [0]) + 1
        vertex_commands = [
            (0, 0, {"sequence": index, "latitude": latitude, "longitude": longitude})
            for index, (latitude, longitude) in enumerate(points, start=1)
        ]
        self.zone_ids = [(0, 0, {
            "name": name or self.env._("Zone %(n)s", n=sequence),
            "sequence": sequence,
            "vertex_ids": vertex_commands,
        })]
        return self

    @api.model
    def _normalize_fence_points(self, points):
        cleaned = []
        for point in points:
            if len(point) != 2:
                raise ValidationError(self.env._("Workplace fence points are not valid."))
            try:
                latitude = float(point[0])
                longitude = float(point[1])
            except (TypeError, ValueError) as error:
                raise ValidationError(self.env._("Workplace fence points are not valid.")) from error
            cleaned.append((latitude, longitude))
        if len(cleaned) >= 2:
            first = cleaned[0]
            last = cleaned[-1]
            if abs(first[0] - last[0]) < 1e-9 and abs(first[1] - last[1]) < 1e-9:
                cleaned = cleaned[:-1]
        return cleaned

    @api.constrains("zone_ids")
    def _check_fence_shape(self):
        for location in self:
            for zone in location.zone_ids:
                zone._validate_shape()

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

    def _contains_gps(self, latitude, longitude):
        self.ensure_one()
        if self._uses_polygon():
            return any(
                zone._contains_gps(latitude, longitude)
                for zone in self._polygon_zones()
            )
        return self._distance_meters(latitude, longitude) <= self.allowed_radius_meters

    def _fence_area_m2(self):
        self.ensure_one()
        if self._uses_polygon():
            return sum(zone._area_m2() for zone in self._polygon_zones())
        return pi * (self.allowed_radius_meters ** 2)

    def _containing_fence_area_m2(self, latitude, longitude):
        """Area used for ranking when this workplace contains the GPS point."""
        self.ensure_one()
        if not self._uses_polygon():
            return pi * (self.allowed_radius_meters ** 2)
        areas = [
            zone._area_m2()
            for zone in self._polygon_zones()
            if zone._contains_gps(latitude, longitude)
        ]
        return min(areas) if areas else self._fence_area_m2()

    @staticmethod
    def _to_local_meters(latitude, longitude, origin_lat, origin_lon):
        meters_north = 111320.0
        meters_east = 111320.0 * cos(radians(origin_lat))
        return (
            (longitude - origin_lon) * meters_east,
            (latitude - origin_lat) * meters_north,
        )

    @staticmethod
    def _point_in_polygon(east, north, points):
        inside = False
        previous = len(points) - 1
        for index, (east_i, north_i) in enumerate(points):
            east_j, north_j = points[previous]
            if (north_i > north) != (north_j > north):
                crossing = (east_j - east_i) * (north - north_i) / (north_j - north_i) + east_i
                if east < crossing:
                    inside = not inside
            previous = index
        return inside

    @staticmethod
    def _distance_to_segment(east, north, start, end):
        start_east, start_north = start
        end_east, end_north = end
        delta_east = end_east - start_east
        delta_north = end_north - start_north
        length_sq = delta_east * delta_east + delta_north * delta_north
        if length_sq == 0:
            return hypot(east - start_east, north - start_north)
        ratio = ((east - start_east) * delta_east + (north - start_north) * delta_north) / length_sq
        ratio = max(0.0, min(1.0, ratio))
        return hypot(
            east - (start_east + ratio * delta_east),
            north - (start_north + ratio * delta_north),
        )

    @staticmethod
    def _polygon_area_m2(points):
        total = 0.0
        count = len(points)
        for index, (east, north) in enumerate(points):
            next_east, next_north = points[(index + 1) % count]
            total += east * next_north - next_east * north
        return abs(total) / 2.0

    @staticmethod
    def _polygon_self_intersects(points):
        count = len(points)
        for index in range(count):
            start = points[index]
            end = points[(index + 1) % count]
            for other in range(index + 1, count):
                if other == index + 1 or (index == 0 and other == count - 1):
                    continue
                if HrAttendanceLocation._segments_intersect(
                    start, end, points[other], points[(other + 1) % count]
                ):
                    return True
        return False

    @staticmethod
    def _segments_intersect(start, end, other_start, other_end):
        def side(origin, first, second):
            value = (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (second[0] - origin[0])
            if abs(value) <= 1e-6:
                return 0
            return 1 if value > 0 else -1

        first_side = side(start, end, other_start)
        second_side = side(start, end, other_end)
        third_side = side(other_start, other_end, start)
        fourth_side = side(other_start, other_end, end)
        return first_side * second_side < 0 and third_side * fourth_side < 0

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

        Prefer the workplace of the employee's department when the GPS point
        is inside it. Otherwise use the workplace whose containing zone is
        smallest. A workplace may have several polygon zones; the point is
        inside if it lies in any of them.
        """
        Department = self.env["hr.department"].sudo()
        home = employee.department_id
        home_location = self._resolved_workplace(home) if home else self.browse()
        if self._company_location_ok(employee, home_location):
            distance = home_location._distance_meters(latitude, longitude)
            if home_location._contains_gps(latitude, longitude):
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
            if not location._contains_gps(latitude, longitude):
                continue
            distance = location._distance_meters(latitude, longitude)
            rank = (location._containing_fence_area_m2(latitude, longitude), distance, department.id)
            if best is None or rank < best[0]:
                best = (rank, location, department, distance)
        if best:
            _rank, location, department, distance = best
            return self._match_result(location, department, distance, gps_accuracy)
        return self.browse(), Department.browse(), "unknown_location", None


class HrAttendanceLocationZone(models.Model):
    _name = "hr.attendance.location.zone"
    _description = "Attendance Workplace Polygon Zone"
    _order = "sequence, id"

    name = fields.Char(required=True, default="Zone 1")
    sequence = fields.Integer(default=1, required=True)
    location_id = fields.Many2one(
        "hr.attendance.location",
        required=True,
        ondelete="cascade",
        index=True,
    )
    vertex_ids = fields.One2many(
        "hr.attendance.location.vertex",
        "zone_id",
        string="Points",
        copy=True,
    )
    point_count = fields.Integer(compute="_compute_point_count", string="Point count")

    @api.depends("vertex_ids")
    def _compute_point_count(self):
        for zone in self:
            zone.point_count = len(zone.vertex_ids)

    def _sorted_vertices(self):
        self.ensure_one()
        return self.vertex_ids.sorted(key=lambda vertex: (vertex.sequence, vertex.id))

    def _points_meters(self):
        self.ensure_one()
        vertices = self._sorted_vertices()
        origin_lat = sum(vertices.mapped("latitude")) / len(vertices)
        origin_lon = sum(vertices.mapped("longitude")) / len(vertices)
        return [
            HrAttendanceLocation._to_local_meters(
                vertex.latitude, vertex.longitude, origin_lat, origin_lon
            )
            for vertex in vertices
        ], origin_lat, origin_lon

    def _area_m2(self):
        self.ensure_one()
        points, _lat, _lon = self._points_meters()
        return HrAttendanceLocation._polygon_area_m2(points)

    def _contains_gps(self, latitude, longitude):
        self.ensure_one()
        if len(self.vertex_ids) < 4:
            return False
        points, origin_lat, origin_lon = self._points_meters()
        east, north = HrAttendanceLocation._to_local_meters(
            latitude, longitude, origin_lat, origin_lon
        )
        if HrAttendanceLocation._point_in_polygon(east, north, points):
            return True
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            if HrAttendanceLocation._distance_to_segment(east, north, start, end) <= 0.5:
                return True
        return False

    def _validate_shape(self):
        self.ensure_one()
        count = len(self.vertex_ids)
        if count == 0:
            return
        if count < 4:
            raise ValidationError(self.env._(
                "Polygon zone \"%(name)s\" needs at least 4 points.",
                name=self.name,
            ))
        points, _lat, _lon = self._points_meters()
        for index, point in enumerate(points):
            other = points[(index + 1) % len(points)]
            if hypot(point[0] - other[0], point[1] - other[1]) < 1:
                raise ValidationError(self.env._(
                    "Fence points in \"%(name)s\" must be at least 1 meter apart.",
                    name=self.name,
                ))
        if HrAttendanceLocation._polygon_self_intersects(points):
            raise ValidationError(self.env._(
                "Fence edges in \"%(name)s\" cannot cross. Draw around the boundary in one direction.",
                name=self.name,
            ))
        if HrAttendanceLocation._polygon_area_m2(points) < 25:
            raise ValidationError(self.env._(
                "Fence points in \"%(name)s\" must outline an area.",
                name=self.name,
            ))

    @api.constrains("vertex_ids")
    def _check_shape(self):
        for zone in self:
            zone._validate_shape()


class HrAttendanceLocationVertex(models.Model):
    _name = "hr.attendance.location.vertex"
    _description = "Attendance Workplace Fence Point"
    _order = "sequence, id"

    zone_id = fields.Many2one(
        "hr.attendance.location.zone",
        ondelete="cascade",
        index=True,
    )
    location_id = fields.Many2one(
        "hr.attendance.location",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=1, required=True)
    latitude = fields.Float(digits=(10, 7), required=True)
    longitude = fields.Float(digits=(10, 7), required=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("zone_id") and not vals.get("location_id"):
                zone = self.env["hr.attendance.location.zone"].browse(vals["zone_id"])
                vals["location_id"] = zone.location_id.id
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("zone_id") and "location_id" not in vals:
            zone = self.env["hr.attendance.location.zone"].browse(vals["zone_id"])
            vals = dict(vals, location_id=zone.location_id.id)
        return super().write(vals)

    @api.constrains("latitude", "longitude")
    def _check_coordinates(self):
        for vertex in self:
            if not -90 <= vertex.latitude <= 90:
                raise ValidationError(self.env._("Latitude must be between -90 and 90."))
            if not -180 <= vertex.longitude <= 180:
                raise ValidationError(self.env._("Longitude must be between -180 and 180."))
