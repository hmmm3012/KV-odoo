# -*- coding: utf-8 -*-

import json
import logging

from odoo import http
from odoo.api import Environment
from odoo.http import request
from odoo.modules.registry import Registry

_logger = logging.getLogger(__name__)


class AttendanceChatbotController(http.Controller):
    def _chatbot(self):
        return request.env["hr.attendance.chatbot"]

    @http.route(
        "/attendance_chatbot/status",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def status(self):
        return self._chatbot().session_status()

    @http.route(
        "/attendance_chatbot/history",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def history(self):
        return self._chatbot().chat_history()

    @http.route(
        "/attendance_chatbot/message_prepare",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def message_prepare(self, text):
        return self._chatbot().message_prepare(text)

    @http.route(
        "/attendance_chatbot/message_stream",
        type="http",
        auth="user",
        methods=["GET"],
        sitemap=False,
    )
    def message_stream(self, user_message_id=None, **kwargs):
        """Server-sent events for assistant completion after message_prepare."""
        if not user_message_id:
            return request.make_response(
                "Missing user_message_id",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=400,
            )

        # Request cursor is closed before Werkzeug drains the generator body.
        dbname = request.env.cr.dbname
        uid = request.env.uid
        context = dict(request.env.context or {})
        user_msg_id = int(user_message_id)

        def generate():
            with Registry(dbname).cursor() as cr:
                try:
                    env = Environment(cr, uid, context)
                    chatbot = env["hr.attendance.chatbot"]
                    for event in chatbot.iter_stream_turn(user_msg_id):
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    cr.commit()
                except Exception as exc:
                    cr.rollback()
                    _logger.exception("Attendance chatbot SSE failed")
                    payload = {"type": "error", "message": str(exc)}
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        headers = {
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return request.make_response(generate(), headers=headers)

    @http.route(
        "/attendance_chatbot/message",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def message(self, text):
        return self._chatbot().chat_send(text)

    @http.route(
        "/attendance_chatbot/confirm",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def confirm(self, proposal_id):
        return self._chatbot().confirm_proposal(proposal_id)

    @http.route(
        "/attendance_chatbot/dismiss",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def dismiss(self, proposal_id):
        return self._chatbot().dismiss_proposal(proposal_id)