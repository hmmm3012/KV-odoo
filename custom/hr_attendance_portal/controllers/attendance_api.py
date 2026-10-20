# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class AttendancePortalController(http.Controller):
    def _portal(self):
        return request.env["hr.attendance.portal"].sudo()

    @http.route(
        ["/attendance", "/attendance/portal"],
        type="http",
        auth="public",
        methods=["GET"],
        sitemap=False,
    )
    def portal_page(self, **kwargs):
        return request.render("hr_attendance_portal.attendance_portal_page", {
            "csrf_token": request.csrf_token(),
        })

    @http.route("/attendance/api/login", type="json", auth="public", methods=["POST"])
    def api_login(self, employee_code, pin, source="personal_web"):
        return self._portal().login(employee_code, pin, source="personal_web")

    @http.route("/attendance/api/logout", type="json", auth="public", methods=["POST"])
    def api_logout(self):
        return self._portal().logout()

    @http.route("/attendance/api/status", type="json", auth="public", methods=["POST"])
    def api_status(self):
        return self._portal().session_status()

    @http.route("/attendance/api/location", type="json", auth="public", methods=["POST"])
    def api_location(self, latitude=False, longitude=False, gps_accuracy=False):
        return self._portal().resolve_location(
            latitude=latitude,
            longitude=longitude,
            gps_accuracy=gps_accuracy,
        )

    @http.route("/attendance/api/face_preview", type="json", auth="public", methods=["POST"])
    def api_face_preview(self, face_image=False):
        return self._portal().preview_face(face_image=face_image)

    @http.route("/attendance/api/check", type="json", auth="public", methods=["POST"])
    def api_check(self, event_type, latitude=False, longitude=False, gps_accuracy=False,
                  request_id=False, source="personal_web", device_identifier=False,
                  face_image=False):
        return self._portal().register(
            event_type=event_type,
            latitude=latitude,
            longitude=longitude,
            gps_accuracy=gps_accuracy,
            request_id=request_id,
            source=source,
            device_identifier=device_identifier,
            face_image=face_image,
        )
