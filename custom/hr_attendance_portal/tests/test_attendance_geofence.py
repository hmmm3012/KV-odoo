# -*- coding: utf-8 -*-

import base64
import json

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import AttendancePortalMixin


def _fence(points):
    return json.dumps([
        {"latitude": latitude, "longitude": longitude}
        for latitude, longitude in points
    ])


SAMPLE_CSV = """WKT,name,description
"POLYGON ((106.6418021 10.7939587, 106.6419712 10.7938965, 106.6421776 10.7943004, 106.6419883 10.7943726, 106.6418021 10.7939587))",KV Import Bau Cat,Gate A
"POLYGON ((106.7116496 10.7771115, 106.7126174 10.7767447, 106.7130858 10.7777533, 106.7121902 10.7782182, 106.7116496 10.7771115))",KV Import TOTT,Main
"""

MULTI_ZONE_CSV = """WKT,name,description
"POLYGON ((110.5000 7.5000, 110.5040 7.5000, 110.5040 7.5040, 110.5000 7.5040, 110.5000 7.5000))",KV Multi Zone Site,North
"POLYGON ((110.5100 7.5100, 110.5140 7.5100, 110.5140 7.5140, 110.5100 7.5140, 110.5100 7.5100))",KV Multi Zone Site,South
"""


@tagged("post_install", "-at_install")
class TestAttendanceGeofence(AttendancePortalMixin, TransactionCase):
    def _draw(self, location, points):
        location.vertex_editor = _fence(points)
        return location

    def _match(self, latitude, longitude, employee=None):
        return self.env["hr.attendance.location"]._match_for_employee(
            employee or self.employee, latitude, longitude
        )

    def test_polygon_contains_inside_and_excludes_nearby_point(self):
        self.location.allowed_radius_meters = 5000
        self._draw(self.location, [
            (7.5000, 110.5000),
            (7.5000, 110.5040),
            (7.5020, 110.5020),
            (7.5040, 110.5040),
            (7.5040, 110.5000),
        ])
        self.assertEqual(self.location.fence_mode, "polygon")
        self.assertEqual(len(self.location.vertex_ids), 5)
        inside, _department, reason, _distance = self._match(7.5020, 110.5010)
        self.assertEqual(inside, self.location)
        self.assertFalse(reason)
        outside, _department, reason, _distance = self._match(7.5020, 110.5030)
        self.assertFalse(outside)
        self.assertEqual(reason, "unknown_location")

    def test_home_polygon_wins_over_smaller_neighbor(self):
        big = [
            (8.0200, 111.8400),
            (8.0200, 111.8700),
            (8.0400, 111.8700),
            (8.0400, 111.8400),
        ]
        small = [
            (8.0300, 111.8550),
            (8.0300, 111.8560),
            (8.0310, 111.8560),
            (8.0310, 111.8550),
        ]
        self._draw(self.location, big)
        neighbor = self.env["hr.attendance.location"].create({
            "name": "Small Site",
            "latitude": 8.0305,
            "longitude": 111.8555,
            "allowed_radius_meters": 50,
            "company_id": self.company.id,
        })
        self._draw(neighbor, small)
        self.env["hr.department"].create({
            "name": "Small Department",
            "company_id": self.company.id,
            "attendance_location_id": neighbor.id,
        })
        location, _department, reason, _distance = self._match(8.0302, 111.8552)
        self.assertEqual(location, self.location)
        self.assertFalse(reason)

    def test_smaller_polygon_wins_when_home_does_not_contain_point(self):
        big = self.env["hr.attendance.location"].create({
            "name": "Big Site",
            "latitude": 8.03,
            "longitude": 111.855,
            "allowed_radius_meters": 50,
            "company_id": self.company.id,
        })
        small = self.env["hr.attendance.location"].create({
            "name": "Small Site",
            "latitude": 8.0305,
            "longitude": 111.8555,
            "allowed_radius_meters": 50,
            "company_id": self.company.id,
        })
        self._draw(big, [
            (8.0200, 111.8400),
            (8.0200, 111.8700),
            (8.0400, 111.8700),
            (8.0400, 111.8400),
        ])
        self._draw(small, [
            (8.0300, 111.8550),
            (8.0300, 111.8560),
            (8.0310, 111.8560),
            (8.0310, 111.8550),
        ])
        self.env["hr.department"].create({
            "name": "Big Department",
            "company_id": self.company.id,
            "attendance_location_id": big.id,
        })
        self.env["hr.department"].create({
            "name": "Small Department",
            "company_id": self.company.id,
            "attendance_location_id": small.id,
        })
        location, _department, reason, _distance = self._match(8.0302, 111.8552)
        self.assertEqual(location, small)
        self.assertFalse(reason)
        self.assertLess(small._fence_area_m2(), big._fence_area_m2())
        self.assertLess(
            big._distance_meters(8.0302, 111.8552),
            small._distance_meters(8.0302, 111.8552),
        )

    def test_clearing_polygon_uses_radius_again(self):
        self._draw(self.location, [
            (7.5000, 110.5000),
            (7.5000, 110.5040),
            (7.5040, 110.5040),
            (7.5040, 110.5000),
        ])
        self.location.vertex_editor = "[]"
        self.assertEqual(self.location.fence_mode, "circle")
        self.location.allowed_radius_meters = 100
        matched, _department, reason, _distance = self._match(self.location.latitude, self.location.longitude)
        self.assertEqual(matched, self.location)
        self.assertFalse(reason)

    def test_crossed_fence_and_wrong_count_are_rejected(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._draw(self.location, [
                (7.50, 110.50),
                (7.51, 110.51),
                (7.50, 110.51),
                (7.51, 110.50),
            ])
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._draw(self.location, [
                (7.50, 110.50),
                (7.51, 110.50),
                (7.51, 110.51),
            ])
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.location.vertex_editor = "not-json"

    def test_six_point_polygon_is_allowed(self):
        self._draw(self.location, [
            (7.5000, 110.5000),
            (7.5000, 110.5030),
            (7.5010, 110.5040),
            (7.5030, 110.5030),
            (7.5040, 110.5010),
            (7.5020, 110.5000),
        ])
        self.assertEqual(self.location.fence_mode, "polygon")
        self.assertEqual(len(self.location.vertex_ids), 6)
        inside, _department, reason, _distance = self._match(7.5020, 110.5020)
        self.assertEqual(inside, self.location)
        self.assertFalse(reason)

    def test_csv_import_updates_department_workplace_by_name(self):
        bau_cat = self.env["hr.department"].create({
            "name": "KV Import Bau Cat",
            "company_id": self.company.id,
            "attendance_location_id": self.location.id,
        })
        tott = self.env["hr.department"].create({
            "name": "KV Import TOTT",
            "company_id": self.company.id,
        })
        wizard = self.env["hr.attendance.location.import.wizard"].create({
            "data_file": base64.b64encode(SAMPLE_CSV.encode("utf-8")),
            "filename": "workplaces.csv",
        })
        wizard.action_import()
        self.assertEqual(len(self.location.zone_ids), 1)
        self.assertEqual(self.location.zone_ids.name, "Gate A")
        self.assertEqual(len(self.location.vertex_ids), 4)
        self.assertEqual(self.location.fence_mode, "polygon")
        self.assertTrue(self.location._contains_gps(10.7941, 106.64195))
        self.assertFalse(self.location._contains_gps(10.80, 106.65))
        self.assertTrue(tott.attendance_location_id)
        self.assertEqual(tott.attendance_location_id.name, "KV Import TOTT")
        self.assertEqual(len(tott.attendance_location_id.vertex_ids), 4)
        self.assertIn("Updated", wizard.result_log)
        self.assertIn("Created", wizard.result_log)
        self.assertEqual(bau_cat.attendance_location_id, self.location)

    def test_workplace_accepts_two_polygon_zones(self):
        self.location._set_fence_zones([
            {
                "name": "North",
                "points": [
                    {"latitude": 7.5000, "longitude": 110.5000},
                    {"latitude": 7.5000, "longitude": 110.5040},
                    {"latitude": 7.5040, "longitude": 110.5040},
                    {"latitude": 7.5040, "longitude": 110.5000},
                ],
            },
            {
                "name": "South",
                "points": [
                    {"latitude": 7.5100, "longitude": 110.5100},
                    {"latitude": 7.5100, "longitude": 110.5140},
                    {"latitude": 7.5140, "longitude": 110.5140},
                    {"latitude": 7.5140, "longitude": 110.5100},
                ],
            },
        ])
        self.assertEqual(self.location.fence_mode, "polygon")
        self.assertEqual(len(self.location.zone_ids), 2)
        self.assertTrue(self.location._contains_gps(7.5020, 110.5020))
        self.assertTrue(self.location._contains_gps(7.5120, 110.5120))
        self.assertFalse(self.location._contains_gps(7.5060, 110.5060))

    def test_csv_import_same_name_creates_multiple_zones(self):
        department = self.env["hr.department"].create({
            "name": "KV Multi Zone Site",
            "company_id": self.company.id,
            "attendance_location_id": self.location.id,
        })
        wizard = self.env["hr.attendance.location.import.wizard"].create({
            "data_file": base64.b64encode(MULTI_ZONE_CSV.encode("utf-8")),
            "filename": "multi.csv",
        })
        wizard.action_import()
        self.assertEqual(department.attendance_location_id, self.location)
        self.assertEqual(len(self.location.zone_ids), 2)
        self.assertEqual(set(self.location.zone_ids.mapped("name")), {"North", "South"})
        self.assertTrue(self.location._contains_gps(7.5020, 110.5020))
        self.assertTrue(self.location._contains_gps(7.5120, 110.5120))
