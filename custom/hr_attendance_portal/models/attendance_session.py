# -*- coding: utf-8 -*-

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.http import request

_logger = logging.getLogger(__name__)

COOKIE_NAME = "attendance_portal_session"


class HrAttendanceSession(models.Model):
    _name = "hr.attendance.session"
    _description = "Attendance Portal Session"
    _order = "create_date desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="cascade")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    token_hash = fields.Char(required=True, index=True)
    source = fields.Selection(
        [("personal_web", "Personal Web"), ("kiosk", "Kiosk")],
        required=True,
        default="personal_web",
    )
    device_id = fields.Many2one("hr.attendance.device", ondelete="set null")
    expires_at = fields.Datetime(required=True, index=True)
    revoked_at = fields.Datetime()
    ip_address = fields.Char()
    user_agent = fields.Char()

    def _hash_token(self, token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @api.model
    def _issue(self, employee, source, ttl_minutes, device=None, ip_address=None, user_agent=None):
        token = secrets.token_urlsafe(32)
        session = self.create({
            "employee_id": employee.id,
            "token_hash": self._hash_token(token),
            "source": source,
            "device_id": device.id if device else False,
            "expires_at": fields.Datetime.now() + timedelta(minutes=ttl_minutes),
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:256],
        })
        return session, token

    @api.model
    def _find_valid(self, token):
        if not token:
            return self.browse()
        token_hash = self._hash_token(token)
        session = self.search([
            ("token_hash", "=", token_hash),
            ("revoked_at", "=", False),
            ("expires_at", ">", fields.Datetime.now()),
        ], limit=1)
        if not session:
            return self.browse()
        if not session.employee_id.active:
            return self.browse()
        return session

    def _revoke(self):
        self.filtered(lambda s: not s.revoked_at).write({"revoked_at": fields.Datetime.now()})

    @api.model
    def _revoke_employee(self, employee, source=None):
        domain = [("employee_id", "=", employee.id), ("revoked_at", "=", False)]
        if source:
            domain.append(("source", "=", source))
        self.search(domain)._revoke()

    def _set_cookie(self, token, ttl_minutes):
        if not request:
            return
        secure = request.httprequest.scheme == "https"
        request.future_response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=max(int(ttl_minutes) * 60, 60),
            httponly=True,
            samesite="Lax",
            secure=secure,
            path="/",
        )

    @api.model
    def _clear_cookie(self):
        if not request:
            return
        request.future_response.set_cookie(
            COOKIE_NAME,
            "",
            max_age=0,
            httponly=True,
            samesite="Lax",
            path="/",
        )

    @api.model
    def _token_from_request(self):
        if not request:
            return False
        return request.httprequest.cookies.get(COOKIE_NAME)

    def _constant_time_equals(self, left, right):
        return hmac.compare_digest(left or "", right or "")

    @api.model
    def _cron_cleanup(self):
        cutoff = fields.Datetime.now() - timedelta(days=7)
        stale = self.search(["|", ("expires_at", "<", cutoff), ("revoked_at", "!=", False)])
        _logger.info("Purging %s attendance portal sessions", len(stale))
        stale.unlink()
