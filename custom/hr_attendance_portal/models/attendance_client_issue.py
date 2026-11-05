# -*- coding: utf-8 -*-

import logging
import re
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

LOCATION_ISSUE_CODES = [
    ("geolocation_timeout", "Không phản hồi quyền vị trí"),
    ("geolocation_denied", "Bị từ chối quyền vị trí"),
    ("missing_gps", "Không lấy được GPS"),
    ("geolocation_insecure", "Không phải HTTPS"),
]

BROWSER_PATTERNS = [
    ("zalo", r"Zalo"),
    ("messenger", r"Orca-Android|MessengerForiOS|Messenger"),
    ("facebook", r"FBAN|FBAV|FB_IAB|FBIOS"),
    ("instagram", r"Instagram"),
    ("other_app", r"Line/|MicroMessenger|TikTok|musical_ly|BytedanceWebview"),
    ("android_webview", r"; wv\)"),
    ("edge", r"EdgA/|EdgiOS/|Edg/"),
    ("samsung", r"SamsungBrowser"),
    ("chrome", r"CriOS/|Chrome/"),
    ("firefox", r"FxiOS/|Firefox/"),
]

DEDUPE_MINUTES = 5
RETENTION_DAYS = 90


class HrAttendanceClientIssue(models.Model):
    _name = "hr.attendance.client.issue"
    _description = "Lỗi vị trí trên portal chấm công"
    _order = "server_time desc, id desc"

    server_time = fields.Datetime(string="Thời gian", required=True, default=fields.Datetime.now, index=True, readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Nhân viên", index=True, ondelete="set null", readonly=True)
    company_id = fields.Many2one("res.company", related="employee_id.company_id", store=True, index=True)
    issue_code = fields.Selection(LOCATION_ISSUE_CODES, string="Lỗi", required=True, index=True, readonly=True)
    browser = fields.Selection(
        [
            ("zalo", "Zalo"),
            ("messenger", "Messenger"),
            ("facebook", "Facebook"),
            ("instagram", "Instagram"),
            ("other_app", "Ứng dụng khác"),
            ("android_webview", "WebView Android"),
            ("ios_webview", "WebView iOS"),
            ("edge", "Edge"),
            ("samsung", "Samsung Internet"),
            ("chrome", "Chrome"),
            ("firefox", "Firefox"),
            ("safari", "Safari"),
            ("other", "Khác"),
        ],
        string="Trình duyệt",
        required=True,
        index=True,
        readonly=True,
    )
    platform = fields.Selection(
        [("android", "Android"), ("ios", "iOS"), ("other", "Khác")],
        string="Hệ điều hành",
        required=True,
        index=True,
        readonly=True,
    )
    user_agent = fields.Char(string="User agent", readonly=True)
    ip_address = fields.Char(string="Địa chỉ IP", readonly=True)

    @api.model
    def _classify_user_agent(self, user_agent):
        user_agent = user_agent or ""
        if re.search(r"Android", user_agent, re.I):
            platform = "android"
        elif re.search(r"iPhone|iPad|iPod", user_agent, re.I):
            platform = "ios"
        else:
            platform = "other"
        for browser, pattern in BROWSER_PATTERNS:
            if re.search(pattern, user_agent, re.I):
                return browser, platform
        if platform == "ios" and "Safari/" not in user_agent:
            return "ios_webview", platform
        if "Safari/" in user_agent:
            return "safari", platform
        return "other", platform

    @api.model
    def _log_issue(self, employee, issue_code, user_agent=False, ip_address=False):
        """Record one location failure, at most once per employee and code every few minutes."""
        if issue_code not in dict(LOCATION_ISSUE_CODES):
            return self.browse()
        recent = self.search([
            ("employee_id", "=", employee.id),
            ("issue_code", "=", issue_code),
            ("server_time", ">=", fields.Datetime.now() - timedelta(minutes=DEDUPE_MINUTES)),
        ], limit=1)
        if recent:
            return recent
        browser, platform = self._classify_user_agent(user_agent)
        return self.create({
            "employee_id": employee.id,
            "issue_code": issue_code,
            "browser": browser,
            "platform": platform,
            "user_agent": user_agent or False,
            "ip_address": ip_address or False,
        })

    @api.model
    def _cron_cleanup(self):
        cutoff = fields.Datetime.now() - timedelta(days=RETENTION_DAYS)
        stale = self.search([("server_time", "<", cutoff)])
        _logger.info("Purging %s attendance portal location issue rows", len(stale))
        stale.unlink()
