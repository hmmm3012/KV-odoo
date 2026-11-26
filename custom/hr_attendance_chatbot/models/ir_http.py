# -*- coding: utf-8 -*-

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        if request.session.uid:
            status = request.env["hr.attendance.chatbot"].session_status()
            info["attendance_chatbot"] = status
        else:
            info["attendance_chatbot"] = {
                "eligible": False,
                "enabled": False,
                "offline_reason": "",
            }
        return info