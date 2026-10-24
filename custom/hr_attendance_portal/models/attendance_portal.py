# -*- coding: utf-8 -*-

import base64
import binascii
import logging
import os
import uuid
from datetime import datetime

import pytz
from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import mute_logger

_logger = logging.getLogger(__name__)

GENERIC_AUTH_ERROR = "invalid_credentials"
PORTAL_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
LOCK_NAMESPACE = 804455
FACE_SLOT_NAMESPACE = 804456
FACE_SLOT_COUNT = max(1, int(os.environ.get("ATTENDANCE_FACE_JOB_SLOTS", "4")))
MAX_FACE_IMAGE_BYTES = 300 * 1024
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

POLICY_REASON_FIELDS = {
    "missing_gps": "attendance_portal_missing_gps_policy",
    "gps_inaccurate": "attendance_portal_gps_inaccurate_policy",
    "outside_geofence": "attendance_portal_outside_geofence_policy",
    "no_location_configured": "attendance_portal_no_location_policy",
    "unknown_location": "attendance_portal_no_location_policy",
    "missing_photo": "attendance_portal_missing_photo_policy",
    "no_face": "attendance_portal_no_face_policy",
    "face_mismatch": "attendance_portal_face_mismatch_policy",
    "face_not_enrolled": "attendance_portal_face_not_enrolled_policy",
}


class HrAttendancePortal(models.AbstractModel):
    _name = "hr.attendance.portal"
    _description = "Attendance Portal Service"

    def _client_ip(self):
        if not request:
            return False
        return request.httprequest.remote_addr

    def _user_agent(self):
        if not request:
            return False
        return (request.httprequest.user_agent.string or "")[:256]

    def _browser(self):
        if not request:
            return False
        return request.httprequest.user_agent.browser

    def _geoip_city(self):
        if not request:
            return False
        return request.geoip.city.name or False

    def _geoip_country(self):
        if not request:
            return False
        return request.geoip.country.name or request.geoip.continent.name or False

    def _company(self, employee=None):
        if employee:
            return employee.company_id
        return self.env.company

    def _lock_employee(self, employee):
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            [LOCK_NAMESPACE, employee.id],
        )

    def _try_acquire_face_slot(self):
        """Non-blocking cap on concurrent YuNet/SFace jobs across HTTP workers."""
        for slot in range(FACE_SLOT_COUNT):
            self.env.cr.execute(
                "SELECT pg_try_advisory_xact_lock(%s, %s)",
                [FACE_SLOT_NAMESPACE, slot],
            )
            if self.env.cr.fetchone()[0]:
                return True
        return False

    def _status_payload(self, employee, extra=None):
        employee.invalidate_recordset(["attendance_state", "last_attendance_id", "last_check_in", "last_check_out"])
        attendance = employee.last_attendance_id.sudo()
        payload = {
            "ok": True,
            "employee_name": employee.name,
            "attendance_state": employee.attendance_state,
            "check_in": attendance.check_in,
            "check_out": attendance.check_out,
            "server_time": fields.Datetime.now(),
        }
        if extra:
            payload.update(extra)
        payload.pop("face_cosine", None)
        return payload

    def _error_payload(self, reason_code, result="rejected", extra=None):
        payload = {
            "ok": False,
            "result": result,
            "error": reason_code,
            "server_time": fields.Datetime.now(),
        }
        if extra:
            payload.update(extra)
        return payload

    def _event_payload(self, event):
        extra = {
            "result": event.result,
            "error": event.failure_reason_code or False,
            "event_type": event.event_type,
            "location_name": self._location_display_name(event.location_id, event.department_id),
        }
        if event.result == "rejected":
            payload = self._error_payload(event.failure_reason_code or "rejected", extra=extra)
            payload["ok"] = False
            if event.employee_id:
                payload.update({
                    "employee_name": event.employee_id.name,
                    "attendance_state": event.employee_id.attendance_state,
                })
            return payload
        payload = self._status_payload(event.employee_id, extra=extra)
        payload["ok"] = True
        payload["result"] = event.result
        return payload

    def _rate_limit_locked(self, employee_code, ip_address, company):
        Attempt = self.env["hr.attendance.auth.attempt"].sudo()
        window = company.attendance_portal_pin_window_minutes or 15
        ip_locked, ip_retry = Attempt._is_locked(
            Attempt._ip_key(ip_address), window
        )
        code_locked, code_retry = Attempt._is_locked(
            Attempt._code_key(employee_code), window
        )
        if ip_locked or code_locked:
            return True, max(ip_retry, code_retry)
        return False, 0

    def _rate_limit_fail(self, employee_code, ip_address, company):
        Attempt = self.env["hr.attendance.auth.attempt"].sudo()
        window = company.attendance_portal_pin_window_minutes or 15
        Attempt._register_failure(
            Attempt._code_key(employee_code),
            window,
            company.attendance_portal_pin_max_attempts or 5,
        )
        Attempt._register_failure(
            Attempt._ip_key(ip_address),
            window,
            company.attendance_portal_ip_max_attempts or 30,
        )

    def _rate_limit_success(self, employee_code, ip_address):
        Attempt = self.env["hr.attendance.auth.attempt"].sudo()
        Attempt._register_success(Attempt._code_key(employee_code))

    @api.model
    def login(self, employee_code, pin, source="personal_web"):
        """Authenticate with employee code + PIN and issue a short-lived session.

        sudo() is used because employees have no Odoo user. Elevation happens only
        after rate limiting, and a session is issued only after PIN verification.
        """
        Employee = self.env["hr.employee"].sudo()
        Session = self.env["hr.attendance.session"].sudo()
        Event = self.env["hr.attendance.event"].sudo()
        company = self.env.company
        ip_address = self._client_ip()
        source = source if source in ("personal_web", "kiosk") else "personal_web"

        locked, retry_after = self._rate_limit_locked(employee_code, ip_address, company)
        if locked:
            Event._log({
                "event_type": "check_in",
                "result": "rejected",
                "source": source,
                "failure_reason_code": "too_many_attempts",
                "ip_address": ip_address,
            })
            return self._error_payload("too_many_attempts", extra={"retry_after": retry_after})

        employee = Employee._attendance_portal_find_by_code(employee_code)
        if not employee:
            Employee._attendance_portal_dummy_verify(pin)
            self._rate_limit_fail(employee_code, ip_address, company)
            return self._error_payload(GENERIC_AUTH_ERROR)

        eligible, reason = employee._attendance_portal_eligible()
        pin_ok = employee._attendance_portal_verify_pin(pin)
        if not eligible or not pin_ok:
            self._rate_limit_fail(employee_code, ip_address, company)
            Event._log({
                "employee_id": employee.id,
                "event_type": "check_in",
                "result": "rejected",
                "source": source,
                "failure_reason_code": reason if not eligible else GENERIC_AUTH_ERROR,
                "ip_address": ip_address,
            })
            return self._error_payload(GENERIC_AUTH_ERROR)

        self._rate_limit_success(employee_code, ip_address)
        if source == "kiosk":
            Session._revoke_employee(employee, source="kiosk")
            ttl = company.attendance_portal_kiosk_session_minutes or 2
        else:
            ttl = company.attendance_portal_session_minutes or 720
        session, token = Session._issue(
            employee,
            source,
            ttl,
            ip_address=ip_address,
            user_agent=self._user_agent(),
        )
        session._set_cookie(token, ttl)
        payload = self._status_payload(employee, extra={"result": "success"})
        return payload

    @api.model
    def logout(self, token=None):
        Session = self.env["hr.attendance.session"].sudo()
        token = token or Session._token_from_request()
        session = Session._find_valid(token)
        if session:
            session._revoke()
        Session._clear_cookie()
        return {"ok": True, "server_time": fields.Datetime.now()}

    @api.model
    def session_status(self, token=None):
        session = self._require_session(token)
        if not session:
            return self._error_payload("invalid_session")
        return self._status_payload(session.employee_id, extra={"result": "success"})

    @api.model
    def attendance_sheet(self, year=False, month=False, token=None):
        """Return one month of the logged-in employee's own shifts."""
        session = self._require_session(token)
        if not session:
            return self._error_payload("invalid_session")
        year, month = self._sheet_month(year, month)
        if not year:
            return self._error_payload("invalid_month")
        start_utc, end_utc = self._sheet_bounds(year, month)
        attendances = self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", session.employee_id.id),
            ("check_in", ">=", start_utc),
            ("check_in", "<", end_utc),
        ], order="check_in desc, id desc")
        rows = [self._sheet_row(attendance) for attendance in attendances]
        total = sum(row.pop("hours_value") for row in rows)
        return {
            "ok": True,
            "year": year,
            "month": month,
            "month_label": "Tháng %s/%s" % (month, year),
            "rows": rows,
            "shift_count": len(rows),
            "total_hours": self._format_sheet_hours(total),
            "server_time": fields.Datetime.now(),
        }

    @api.model
    def _sheet_month(self, year, month):
        now = datetime.now(PORTAL_TZ)
        if not year and not month:
            return now.year, now.month
        try:
            year = int(year)
            month = int(month)
        except (TypeError, ValueError):
            return False, False
        if year < 2000 or year > 2100 or month < 1 or month > 12:
            return False, False
        return year, month

    @api.model
    def _sheet_bounds(self, year, month):
        start = PORTAL_TZ.localize(datetime(year, month, 1))
        if month == 12:
            end = PORTAL_TZ.localize(datetime(year + 1, 1, 1))
        else:
            end = PORTAL_TZ.localize(datetime(year, month + 1, 1))
        return (
            start.astimezone(pytz.UTC).replace(tzinfo=None),
            end.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    @api.model
    def _sheet_row(self, attendance):
        check_in = self._sheet_local(attendance.check_in)
        check_out = self._sheet_local(attendance.check_out)
        hours = attendance.recognized_regular_hours or 0.0
        return {
            "date": check_in.strftime("%d/%m/%Y") if check_in else "",
            "check_in": check_in.strftime("%H:%M") if check_in else "",
            "check_out": check_out.strftime("%H:%M") if check_out else "",
            "hours": self._format_sheet_hours(hours),
            "hours_value": hours,
            "note": self._sheet_note(attendance),
        }

    @api.model
    def _sheet_local(self, value):
        if not value:
            return False
        return pytz.UTC.localize(value).astimezone(PORTAL_TZ)

    @api.model
    def _sheet_note(self, attendance):
        if attendance.session_state == "denied":
            return "Từ chối"
        if not attendance.check_out:
            if attendance.exception_code == "missing_checkout":
                return "Quên giờ ra"
            return "Chưa ra"
        if attendance.overtime_state in ("pending_captain", "pending_hr_review"):
            return "Chờ duyệt làm thêm"
        return ""

    @api.model
    def _format_sheet_hours(self, hours):
        minutes = int(round((hours or 0.0) * 60))
        if minutes < 0:
            minutes = 0
        whole, remainder = divmod(minutes, 60)
        return "%d:%02d" % (whole, remainder)

    @api.model
    def resolve_location(self, latitude=False, longitude=False, gps_accuracy=False, token=None):
        """Match GPS to a workplace for the logged-in employee. Does not punch."""
        session = self._require_session(token)
        if not session:
            return self._error_payload("invalid_session")
        employee = session.employee_id.sudo()
        source = session.source or "personal_web"
        location, department, reason, distance = self._validate_location(
            employee, source, latitude, longitude, gps_accuracy, device=False,
        )
        return {
            "ok": True,
            "location_name": self._location_display_name(location, department),
            "distance_meters": distance,
            "error": reason or False,
            "server_time": fields.Datetime.now(),
        }

    def _require_session(self, token=None):
        Session = self.env["hr.attendance.session"].sudo()
        token = token or Session._token_from_request()
        return Session._find_valid(token)

    def _resolve_device(self, device_identifier):
        if not device_identifier:
            return self.env["hr.attendance.device"].browse()
        device = self.env["hr.attendance.device"].sudo().search([
            ("device_identifier", "=", device_identifier),
        ], limit=1)
        return device

    def _policy_result(self, company, reason_code):
        if reason_code in ("face_check_unavailable", "face_mismatch"):
            return "needs_review"
        field_name = POLICY_REASON_FIELDS.get(reason_code)
        if not field_name:
            return "rejected"
        return getattr(company, field_name) or "rejected"

    def _parse_face_image(self, face_image):
        """Return (jpeg/png bytes, False) or (False, 'missing_photo'). Never logs the payload."""
        if not face_image:
            return False, "missing_photo"
        if isinstance(face_image, bytes):
            data = face_image
            if data.startswith(b"data:"):
                try:
                    face_image = data.decode("ascii", errors="strict")
                except UnicodeDecodeError:
                    return False, "missing_photo"
            elif data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC):
                if len(data) > MAX_FACE_IMAGE_BYTES:
                    return False, "missing_photo"
                return data, False
            else:
                try:
                    face_image = data.decode("ascii", errors="strict")
                except UnicodeDecodeError:
                    return False, "missing_photo"
        if not isinstance(face_image, str):
            return False, "missing_photo"
        raw = face_image.strip()
        if not raw:
            return False, "missing_photo"
        if raw.startswith("data:"):
            header, _, payload = raw.partition(",")
            mime = header.split(";")[0][5:].lower()
            if mime not in ("image/jpeg", "image/jpg", "image/png"):
                return False, "missing_photo"
            raw = payload
        try:
            data = base64.b64decode(raw, validate=False)
        except (binascii.Error, ValueError):
            return False, "missing_photo"
        if not data or len(data) > MAX_FACE_IMAGE_BYTES:
            return False, "missing_photo"
        if not (data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC)):
            return False, "missing_photo"
        return data, False

    def _validate_face_image(self, face_image, source):
        if source == "kiosk" and not face_image:
            return False, False
        data, reason = self._parse_face_image(face_image)
        return data, reason

    def _detect_faces(self, photo_bytes):
        """Return (face_count, reason) for a validated JPEG/PNG payload."""
        from .face_detection import detect_face_count
        return detect_face_count(photo_bytes)

    def _analyze_face_image(self, photo_bytes):
        from .face_pipeline import process_face
        return process_face(photo_bytes)

    def _process_punch_face(self, photo_bytes, employee):
        """Run detect → quality → 1:1 cosine against this employee's enrolled vector."""
        from .face_pipeline import QUALITY_RECAPTURE, compare_embeddings, unpack_embedding

        analyzed = self._analyze_face_image(photo_bytes)
        result = {
            "unavailable": bool(analyzed.get("unavailable")),
            "face_count": analyzed.get("face_count") or 0,
            "quality_reason": analyzed.get("quality_reason") or False,
            "verify_reason": False,
            "force_reject": False,
            "cosine": None,
        }
        if result["unavailable"]:
            result["quality_reason"] = False
            result["verify_reason"] = "face_check_unavailable"
            return result
        quality = result["quality_reason"]
        if quality:
            result["force_reject"] = quality in QUALITY_RECAPTURE
            return result
        enrolled = unpack_embedding(
            employee.sudo().with_context(bin_size=False).attendance_face_embedding
        )
        if not enrolled:
            result["verify_reason"] = "face_not_enrolled"
            return result
        score, reason, force_reject = compare_embeddings(analyzed.get("embedding"), enrolled)
        result["cosine"] = score
        result["verify_reason"] = reason
        result["force_reject"] = force_reject
        return result

    @api.model
    def preview_face(self, face_image=False, token=None):
        """Quality-only check. Does not punch and never returns embeddings."""
        session = self._require_session(token)
        if not session:
            return self._error_payload("invalid_session")
        data, parse_reason = self._parse_face_image(face_image)
        if parse_reason:
            return {
                "ok": False,
                "result": "rejected",
                "error": parse_reason,
                "reason": parse_reason,
                "server_time": fields.Datetime.now(),
            }
        from .face_pipeline import QUALITY_RECAPTURE

        analyzed = self._analyze_face_image(data)
        reason = False
        if not analyzed.get("unavailable"):
            reason = analyzed.get("quality_reason") or False
        if reason in QUALITY_RECAPTURE:
            return {
                "ok": False,
                "result": "rejected",
                "error": reason,
                "reason": reason,
                "server_time": fields.Datetime.now(),
            }
        return {
            "ok": True,
            "reason": False,
            "error": False,
            "server_time": fields.Datetime.now(),
        }

    def _policy_outcome(self, company, reasons):
        review_reason = False
        for reason in reasons:
            if not reason:
                continue
            if self._policy_result(company, reason) == "reject":
                return reason, False
            if not review_reason:
                review_reason = reason
        return False, review_reason

    def _empty_location(self):
        return self.env["hr.attendance.location"].browse()

    def _empty_department(self):
        return self.env["hr.department"].browse()

    def _location_display_name(self, location, department=None):
        if department:
            return department.name or False
        return location.name if location else False

    def _validate_location(self, employee, source, latitude, longitude, gps_accuracy, device):
        company = employee.company_id
        has_gps = latitude not in (None, False) and longitude not in (None, False)
        if not has_gps:
            if source == "kiosk" and not company.attendance_portal_kiosk_require_gps:
                location = device.location_id if device else self._empty_location()
                return location, self._empty_department(), False, None
            return self._empty_location(), self._empty_department(), "missing_gps", None

        location, department, reason, distance = self.env["hr.attendance.location"].sudo()._match_for_employee(
            employee, latitude, longitude, gps_accuracy=gps_accuracy
        )
        return location, department, reason, distance

    @api.model
    def register(self, event_type, latitude=False, longitude=False, gps_accuracy=False,
                 request_id=False, source="personal_web", device_identifier=False,
                 face_image=False, token=None):
        """Check in or out for the authenticated employee.

        sudo() is scoped to the session-authenticated employee after eligibility
        and location validation. Attendance is written with the employee's id only.
        """
        Event = self.env["hr.attendance.event"].sudo()
        ip_address = self._client_ip()

        if event_type not in ("check_in", "check_out"):
            return self._error_payload("invalid_event_type")

        session = self._require_session(token)
        if not session:
            return self._error_payload("invalid_session")

        employee = session.employee_id.sudo()
        source = session.source or "personal_web"

        eligible, reason = employee._attendance_portal_eligible()
        if not eligible:
            Event._log({
                "employee_id": employee.id,
                "event_type": event_type,
                "result": "rejected",
                "source": source,
                "request_id": request_id or None,
                "failure_reason_code": reason,
                "ip_address": ip_address,
            })
            return self._error_payload(reason)

        device = self._resolve_device(device_identifier)
        if device_identifier:
            if not device or not device._is_usable():
                Event._log({
                    "employee_id": employee.id,
                    "event_type": event_type,
                    "result": "rejected",
                    "source": source,
                    "request_id": request_id or None,
                    "device_id": device.id if device else False,
                    "failure_reason_code": "device_revoked",
                    "ip_address": ip_address,
                })
                return self._error_payload("device_revoked")
            device.sudo().write({"last_seen_at": fields.Datetime.now()})

        request_id = (request_id or "").strip() or str(uuid.uuid4())
        existing = Event.search([("request_id", "=", request_id)], limit=1)
        if existing:
            if existing.employee_id != employee:
                return self._error_payload("duplicate_request")
            return self._event_payload(existing)

        self._lock_employee(employee)
        employee.invalidate_recordset(["attendance_state", "last_attendance_id"])

        existing = Event.search([("request_id", "=", request_id)], limit=1)
        if existing:
            if existing.employee_id != employee:
                return self._error_payload("duplicate_request")
            return self._event_payload(existing)

        location, department, location_reason, distance = self._validate_location(
            employee, source, latitude, longitude, gps_accuracy, device
        )
        photo_bytes, photo_reason = self._validate_face_image(face_image, source)
        photo_b64 = base64.b64encode(photo_bytes).decode("ascii") if photo_bytes else False
        face_count = 0
        face_reason = False
        face_cosine = False
        recapture = False
        force_reject = False
        if photo_bytes:
            if not self._try_acquire_face_slot():
                return self._error_payload("server_busy", extra={"retry_after": 3})
            processed = self._process_punch_face(photo_bytes, employee)
            face_count = processed.get("face_count") or 0
            face_cosine = processed.get("cosine")
            recapture = bool(processed.get("quality_reason"))
            force_reject = bool(processed.get("force_reject"))
            face_reason = (
                processed.get("quality_reason")
                or processed.get("verify_reason")
                or False
            )

        event_vals = {
            "employee_id": employee.id,
            "event_type": event_type,
            "source": source,
            "request_id": request_id,
            "latitude": latitude or False,
            "longitude": longitude or False,
            "gps_accuracy": gps_accuracy or False,
            "distance_meters": distance,
            "location_id": location.id if location else False,
            "department_id": department.id if department else False,
            "device_id": device.id if device else False,
            "ip_address": ip_address,
            "face_image": photo_b64,
            "face_count": face_count,
            "face_cosine": face_cosine if face_cosine is not None else False,
        }

        if recapture or force_reject:
            reject_reason, review_reason = face_reason, False
        else:
            reject_reason, review_reason = self._policy_outcome(
                employee.company_id, [photo_reason, face_reason, location_reason]
            )
        if reject_reason:
            event_vals.update({
                "result": "rejected",
                "failure_reason_code": reject_reason,
            })
            event = self._create_event(event_vals)
            return self._event_payload(event)

        expected_state = "checked_out" if event_type == "check_in" else "checked_in"
        if employee.attendance_state != expected_state:
            state_reason = "already_checked_in" if event_type == "check_in" else "not_checked_in"
            event_vals.update({
                "result": "rejected",
                "failure_reason_code": state_reason,
            })
            event = self._create_event(event_vals)
            return self._event_payload(event)

        geo_information = {
            "city": self._geoip_city() or False,
            "country_name": self._geoip_country() or False,
            "latitude": latitude or False,
            "longitude": longitude or False,
            "ip_address": ip_address or False,
            "browser": self._browser() or False,
            "mode": source,
        }
        attendance = employee._attendance_action_change(geo_information)
        extra_attendance = {}
        if event_type == "check_in":
            extra_attendance["in_location_id"] = location.id if location else False
            extra_attendance["in_department_id"] = department.id if department else False
            extra_attendance["in_gps_accuracy"] = gps_accuracy or False
            extra_attendance["in_face_image"] = photo_b64
            extra_attendance["in_face_detected"] = bool(face_count)
            extra_attendance["portal_review_status"] = "pending" if review_reason else "not_required"
        else:
            extra_attendance["out_location_id"] = location.id if location else False
            extra_attendance["out_department_id"] = department.id if department else False
            extra_attendance["out_gps_accuracy"] = gps_accuracy or False
            extra_attendance["out_face_image"] = photo_b64
            extra_attendance["out_face_detected"] = bool(face_count)
            if review_reason:
                extra_attendance["portal_review_status"] = "pending"
        if extra_attendance:
            attendance.sudo().write(extra_attendance)

        event_vals.update({
            "attendance_id": attendance.id,
            "result": "needs_review" if review_reason else "success",
            "failure_reason_code": review_reason or False,
            "review_status": "pending" if review_reason else "not_required",
        })
        event = self._create_event(event_vals)

        if source == "kiosk":
            session._revoke()
            self.env["hr.attendance.session"].sudo()._clear_cookie()

        return self._event_payload(event)

    def _create_event(self, values):
        Event = self.env["hr.attendance.event"].sudo()
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                return Event._log(values)
        except (IntegrityError, ValidationError):
            existing = Event.search([("request_id", "=", values.get("request_id"))], limit=1)
            if existing:
                return existing
            raise

    @api.model
    def register_for_employee(self, employee, event_type, latitude=False, longitude=False,
                              gps_accuracy=False, request_id=False, source="kiosk",
                              device_identifier=False, face_image=False):
        """Shared-device/kiosk entry that authenticates the employee separately.

        Used by the kiosk controller after PIN/barcode verification. Still runs
        geofence, idempotency, locking, and audit logging.
        """
        Session = self.env["hr.attendance.session"].sudo()
        company = employee.company_id
        ttl = company.attendance_portal_kiosk_session_minutes or 2
        Session._revoke_employee(employee, source="kiosk")
        session, token = Session._issue(
            employee,
            "kiosk",
            ttl,
            ip_address=self._client_ip(),
            user_agent=self._user_agent(),
        )
        try:
            return self.register(
                event_type=event_type,
                latitude=latitude,
                longitude=longitude,
                gps_accuracy=gps_accuracy,
                request_id=request_id,
                source="kiosk",
                device_identifier=device_identifier,
                face_image=face_image,
                token=token,
            )
        finally:
            session._revoke()
            Session._clear_cookie()
