# -*- coding: utf-8 -*-

import uuid

from odoo import http
from odoo.addons.hr_attendance.controllers.main import HrAttendance
from odoo.http import request


class HrAttendanceKioskPortal(HrAttendance):
    def _portal_event_type(self, employee):
        return "check_out" if employee.attendance_state == "checked_in" else "check_in"

    def _register_kiosk(self, employee, latitude=False, longitude=False):
        return request.env["hr.attendance.portal"].sudo().register_for_employee(
            employee=employee,
            event_type=self._portal_event_type(employee),
            latitude=latitude,
            longitude=longitude,
            request_id=str(uuid.uuid4()),
            source="kiosk",
        )

    @http.route("/hr_attendance/attendance_barcode_scanned", type="json", auth="public")
    def scan_barcode(self, token, barcode):
        company = self._get_company(token)
        if not company:
            return {}
        employee = request.env["hr.employee"].sudo().search([
            ("barcode", "=", barcode),
            ("company_id", "=", company.id),
        ], limit=1)
        if not employee:
            return {}
        result = self._register_kiosk(employee)
        if not result.get("ok") and result.get("result") != "needs_review":
            return {}
        return self._get_employee_info_response(employee)

    @http.route("/hr_attendance/manual_selection", type="json", auth="public")
    def manual_selection_with_geolocation(self, token, employee_id, pin_code, latitude=False, longitude=False):
        company = self._get_company(token)
        if not company:
            return {}
        employee = request.env["hr.employee"].sudo().browse(employee_id)
        if not employee.exists() or employee.company_id != company:
            return {}
        if company.attendance_kiosk_use_pin and not employee._attendance_portal_verify_pin(pin_code or ""):
            return {}
        result = self._register_kiosk(employee, latitude=latitude, longitude=longitude)
        if not result.get("ok") and result.get("result") != "needs_review":
            return {}
        return self._get_employee_info_response(employee)
