# -*- coding: utf-8 -*-

from unittest.mock import patch

# 1x1 JPEG used as punch-photo evidence in tests (audit only, not recognition).
TINY_JPEG_B64 = (
    "/9j/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8Q"
    "EBEQCgwSExIQEw8QEBD/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAA//EABQQAQAA"
    "AAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AN//Z"
)


class AttendancePortalMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal = cls.env["hr.attendance.portal"]
        cls.company = cls.env.company
        cls.employee = cls.env["hr.employee"].create({
            "name": "Portal Employee",
            "emp_code": "KV-PORTAL-001",
            "pin": "1357",
            "attendance_portal_enabled": True,
            "company_id": cls.company.id,
        })
        cls.location = cls.env["hr.attendance.location"].create({
            "name": "Van Phong HCM",
            "latitude": 10.8231,
            "longitude": 106.6297,
            "allowed_radius_meters": 250,
            "max_gps_accuracy_meters": 80,
            "company_id": cls.company.id,
        })
        cls.department = cls.env["hr.department"].create({
            "name": "Portal Site",
            "company_id": cls.company.id,
            "attendance_location_id": cls.location.id,
        })
        cls.employee.department_id = cls.department

    def setUp(self):
        super().setUp()
        self.punch_face_result = {
            "unavailable": False,
            "face_count": 1,
            "quality_reason": False,
            "verify_reason": False,
            "force_reject": False,
            "cosine": 0.82,
        }
        patcher = patch.object(
            type(self.env["hr.attendance.portal"]),
            "_process_punch_face",
            side_effect=lambda _photo_bytes, _employee: dict(self.punch_face_result),
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def _login(self, code="KV-PORTAL-001", pin="1357", source="personal_web"):
        return self.portal.login(code, pin, source=source)

    def _issue_token(self, employee=None, source="personal_web"):
        employee = employee or self.employee
        session, token = self.env["hr.attendance.session"]._issue(employee, source, 60)
        return session, token

    def _register(self, token, event_type="check_in", request_id="req-1", **kwargs):
        values = {
            "latitude": 10.8231,
            "longitude": 106.6297,
            "gps_accuracy": 12,
            "face_image": TINY_JPEG_B64,
            "request_id": request_id,
            "source": "personal_web",
        }
        values.update(kwargs)
        return self.portal.register(event_type, token=token, **values)
