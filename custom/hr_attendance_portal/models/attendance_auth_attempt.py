# -*- coding: utf-8 -*-

import hashlib
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrAttendanceAuthAttempt(models.Model):
    _name = "hr.attendance.auth.attempt"
    _description = "Attendance Portal Auth Attempt"
    _order = "write_date desc"

    key = fields.Char(required=True, index=True)
    failed_count = fields.Integer(default=0)
    window_start = fields.Datetime(required=True)
    locked_until = fields.Datetime(index=True)

    _sql_constraints = [
        ("key_uniq", "unique(key)", "Auth attempt key must be unique."),
    ]

    @api.model
    def _hash_identifier(self, value):
        normalized = (value or "").strip().encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    @api.model
    def _ip_key(self, ip_address):
        return "ip:%s" % self._hash_identifier(ip_address or "unknown")

    @api.model
    def _code_key(self, employee_code):
        return "code:%s" % self._hash_identifier(employee_code)

    @api.model
    def _get_or_create(self, key):
        record = self.search([("key", "=", key)], limit=1)
        if record:
            return record
        return self.create({
            "key": key,
            "failed_count": 0,
            "window_start": fields.Datetime.now(),
        })

    def _reset_if_window_expired(self, window_minutes):
        self.ensure_one()
        now = fields.Datetime.now()
        if self.window_start and now - self.window_start > timedelta(minutes=window_minutes):
            self.write({
                "failed_count": 0,
                "window_start": now,
                "locked_until": False,
            })

    def _lockout_minutes(self, failed_count, max_attempts):
        if failed_count < max_attempts:
            return 0
        extra = failed_count - max_attempts
        if extra >= 7:
            return 15
        if extra >= 3:
            return 5
        return 1

    @api.model
    def _is_locked(self, key, window_minutes):
        record = self._get_or_create(key)
        record._reset_if_window_expired(window_minutes)
        if record.locked_until and record.locked_until > fields.Datetime.now():
            remaining = int((record.locked_until - fields.Datetime.now()).total_seconds())
            return True, max(remaining, 1)
        return False, 0

    @api.model
    def _register_failure(self, key, window_minutes, max_attempts):
        record = self._get_or_create(key)
        record._reset_if_window_expired(window_minutes)
        count = record.failed_count + 1
        values = {"failed_count": count}
        if not record.window_start:
            values["window_start"] = fields.Datetime.now()
        lock_minutes = record._lockout_minutes(count, max_attempts)
        if lock_minutes:
            values["locked_until"] = fields.Datetime.now() + timedelta(minutes=lock_minutes)
        record.write(values)
        return record

    @api.model
    def _register_success(self, key):
        record = self.search([("key", "=", key)], limit=1)
        if record:
            record.write({
                "failed_count": 0,
                "window_start": fields.Datetime.now(),
                "locked_until": False,
            })

    @api.model
    def _cron_cleanup(self):
        cutoff = fields.Datetime.now() - timedelta(days=2)
        stale = self.search([("write_date", "<", cutoff)])
        _logger.info("Purging %s attendance auth attempt rows", len(stale))
        stale.unlink()
