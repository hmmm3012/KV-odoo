# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import AttendancePortalMixin


@tagged("post_install", "-at_install")
class TestAttendancePublicIp(AttendancePortalMixin, TransactionCase):
    def _match(self, latitude, longitude, gps_accuracy=None, client_ip=None, employee=None):
        return self.env["hr.attendance.location"]._match_for_employee(
            employee or self.employee,
            latitude,
            longitude,
            gps_accuracy=gps_accuracy,
            client_ip=client_ip,
        )

    def _enable_wifi(self, location, ips):
        location.write({
            "wifi_punch_enabled": True,
            "allowed_public_ips": ips,
        })
        return location

    def _other_site(self, name="Other Lot", **vals):
        location = self.env["hr.attendance.location"].create({
            "name": name,
            "latitude": 21.0285,
            "longitude": 105.8542,
            "allowed_radius_meters": 80,
            "company_id": self.company.id,
            **vals,
        })
        department = self.env["hr.department"].create({
            "name": "%s Department" % name,
            "company_id": self.company.id,
            "attendance_location_id": location.id,
        })
        return location, department

    def test_cidr_matches_address_inside_range(self):
        self._enable_wifi(self.location, "203.0.113.0/24\n2001:db8::/32")
        location, department, reason, _distance = self._match(
            False, False, client_ip="203.0.113.44"
        )
        self.assertEqual(location, self.location)
        self.assertEqual(department, self.department)
        self.assertFalse(reason)

        v6, _department, reason, _distance = self._match(
            False, False, client_ip="2001:db8::10"
        )
        self.assertEqual(v6, self.location)
        self.assertFalse(reason)

        mapped, _department, reason, _distance = self._match(
            False, False, client_ip="::ffff:203.0.113.9"
        )
        self.assertEqual(mapped, self.location)
        self.assertFalse(reason)

    def test_unique_site_ip_assigns_workplace_without_gps(self):
        other, other_department = self._other_site()
        self._enable_wifi(other, "198.51.100.10")
        location, department, reason, distance = self._match(
            False, False, client_ip="198.51.100.10"
        )
        self.assertEqual(location, other)
        self.assertEqual(department, other_department)
        self.assertFalse(reason)
        self.assertFalse(distance)

    def test_no_ip_match_keeps_unknown_or_missing_gps(self):
        self._enable_wifi(self.location, "203.0.113.10")
        unknown, _department, reason, _distance = self._match(
            16.0, 108.0, client_ip="198.51.100.1"
        )
        self.assertFalse(unknown)
        self.assertEqual(reason, "unknown_location")

        missing, _department, reason, _distance = self._match(
            False, False, client_ip="198.51.100.1"
        )
        self.assertFalse(missing)
        self.assertEqual(reason, "missing_gps")

        none, _department, reason, _distance = self._match(False, False, client_ip=None)
        self.assertFalse(none)
        self.assertEqual(reason, "missing_gps")

    def test_untrusted_gps_falls_through_to_unique_ip(self):
        other, other_department = self._other_site()
        self._enable_wifi(other, "198.51.100.10")
        self.location.max_gps_accuracy_meters = 20
        location, department, reason, distance = self._match(
            self.location.latitude,
            self.location.longitude,
            gps_accuracy=80,
            client_ip="198.51.100.10",
        )
        self.assertEqual(location, other)
        self.assertEqual(department, other_department)
        self.assertFalse(reason)
        self.assertFalse(distance)

        near_edge_lat = self.location.latitude + (230.0 / 111320.0)
        self.location.max_gps_accuracy_meters = 80
        self.assertLess(
            self.location._distance_meters(near_edge_lat, self.location.longitude),
            self.location.allowed_radius_meters,
        )
        self.assertFalse(self.location._accuracy_circle_inside(
            near_edge_lat, self.location.longitude, 40,
        ))
        edged, edged_department, reason, _distance = self._match(
            near_edge_lat,
            self.location.longitude,
            gps_accuracy=40,
            client_ip="198.51.100.10",
        )
        self.assertEqual(edged, other)
        self.assertEqual(edged_department, other_department)
        self.assertFalse(reason)

        self.location.max_gps_accuracy_meters = 20
        flagged, _department, reason, _distance = self._match(
            self.location.latitude,
            self.location.longitude,
            gps_accuracy=80,
            client_ip="203.0.113.10",
        )
        self.assertEqual(flagged, self.location)
        self.assertEqual(reason, "gps_inaccurate")

    def test_gps_inside_fence_wins_over_other_site_ip(self):
        other, _other_department = self._other_site()
        self._enable_wifi(other, "203.0.113.10")
        location, department, reason, _distance = self._match(
            self.location.latitude,
            self.location.longitude,
            gps_accuracy=12,
            client_ip="203.0.113.10",
        )
        self.assertEqual(location, self.location)
        self.assertEqual(department, self.department)
        self.assertFalse(reason)

    def test_inaccurate_gps_is_accepted_when_ip_matches_same_site(self):
        self._enable_wifi(self.location, "203.0.113.10")
        self.location.max_gps_accuracy_meters = 20
        flagged, _department, reason, _distance = self._match(
            self.location.latitude,
            self.location.longitude,
            gps_accuracy=80,
        )
        self.assertEqual(flagged, self.location)
        self.assertEqual(reason, "gps_inaccurate")

        accepted, department, reason, _distance = self._match(
            self.location.latitude,
            self.location.longitude,
            gps_accuracy=80,
            client_ip="203.0.113.10",
        )
        self.assertEqual(accepted, self.location)
        self.assertEqual(department, self.department)
        self.assertFalse(reason)

    def test_shared_ip_prefers_home_workplace(self):
        other, _other_department = self._other_site()
        self._enable_wifi(self.location, "203.0.113.10")
        self._enable_wifi(other, "203.0.113.10")
        location, department, reason, _distance = self._match(
            False, False, client_ip="203.0.113.10"
        )
        self.assertEqual(location, self.location)
        self.assertEqual(department, self.department)
        self.assertFalse(reason)

    def test_ambiguous_ip_without_home_match_is_ignored(self):
        first, _first_department = self._other_site("Lot A")
        second, _second_department = self._other_site("Lot B")
        self._enable_wifi(first, "203.0.113.10")
        self._enable_wifi(second, "203.0.113.10")
        location, _department, reason, _distance = self._match(
            False, False, client_ip="203.0.113.10"
        )
        self.assertFalse(location)
        self.assertEqual(reason, "missing_gps")

    def test_invalid_public_ip_text_is_rejected(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.location.allowed_public_ips = "not-an-ip"

    def test_register_uses_client_ip_when_gps_is_missing(self):
        self._enable_wifi(self.location, "203.0.113.0/24")
        _, token = self._issue_token()
        with patch.object(type(self.portal), "_client_ip", return_value="203.0.113.44"):
            result = self._register(
                token,
                "check_in",
                request_id="ip-in-1",
                latitude=False,
                longitude=False,
                gps_accuracy=False,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "success")
        self.assertEqual(result["location_name"], "Van Phong HCM")
        attendance = self.env["hr.attendance"].search(
            [("employee_id", "=", self.employee.id)], limit=1
        )
        self.assertEqual(attendance.in_location_id, self.location)
        event = self.env["hr.attendance.event"].search([("request_id", "=", "ip-in-1")])
        self.assertEqual(event.ip_address, "203.0.113.44")
        self.assertEqual(event.location_id, self.location)
        self.assertEqual(event.result, "success")

    def test_register_gps_fallback_ignores_other_site_ip(self):
        other, _other_department = self._other_site()
        self._enable_wifi(other, "198.51.100.10")
        _, token = self._issue_token()
        with patch.object(type(self.portal), "_client_ip", return_value="198.51.100.10"):
            result = self._register(token, "check_in", request_id="gps-wins")
        self.assertTrue(result["ok"])
        self.assertEqual(result["location_name"], "Van Phong HCM")
        attendance = self.env["hr.attendance"].search(
            [("employee_id", "=", self.employee.id)], limit=1
        )
        self.assertEqual(attendance.in_location_id, self.location)
        self.assertNotEqual(attendance.in_location_id, other)
        event = self.env["hr.attendance.event"].search([("request_id", "=", "gps-wins")])
        self.assertEqual(event.ip_address, "198.51.100.10")

    def test_wifi_punch_flag_off_ignores_ip(self):
        self.location.allowed_public_ips = "203.0.113.10"
        self.assertFalse(self.location.wifi_punch_enabled)

        missing, _department, reason, _distance = self._match(
            False, False, client_ip="203.0.113.10"
        )
        self.assertFalse(missing)
        self.assertEqual(reason, "missing_gps")

        unknown, _department, reason, _distance = self._match(
            16.0, 108.0, client_ip="203.0.113.10"
        )
        self.assertFalse(unknown)
        self.assertEqual(reason, "unknown_location")

        self.location.max_gps_accuracy_meters = 20
        flagged, _department, reason, _distance = self._match(
            self.location.latitude,
            self.location.longitude,
            gps_accuracy=80,
            client_ip="203.0.113.10",
        )
        self.assertEqual(flagged, self.location)
        self.assertEqual(reason, "gps_inaccurate")

        inside, department, reason, _distance = self._match(
            self.location.latitude,
            self.location.longitude,
            gps_accuracy=12,
            client_ip="203.0.113.10",
        )
        self.assertEqual(inside, self.location)
        self.assertEqual(department, self.department)
        self.assertFalse(reason)

    def test_wifi_punch_on_without_ips_stays_gps_only(self):
        self.location.wifi_punch_enabled = True
        missing, _department, reason, _distance = self._match(
            False, False, client_ip="203.0.113.10"
        )
        self.assertFalse(missing)
        self.assertEqual(reason, "missing_gps")

    def test_register_flag_off_ignores_matching_ip(self):
        self.location.allowed_public_ips = "203.0.113.44"
        _, token = self._issue_token()
        with patch.object(type(self.portal), "_client_ip", return_value="203.0.113.44"):
            result = self._register(
                token,
                "check_in",
                request_id="flag-off",
                latitude=False,
                longitude=False,
                gps_accuracy=False,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "missing_gps")
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))
        event = self.env["hr.attendance.event"].search([("request_id", "=", "flag-off")])
        self.assertEqual(event.ip_address, "203.0.113.44")
        self.assertFalse(event.location_id)
