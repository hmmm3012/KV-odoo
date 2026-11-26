# -*- coding: utf-8 -*-

import json

from odoo import http
from odoo.http import request


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

        def generate():
            chatbot = request.env["hr.attendance.chatbot"]
            for event in chatbot.iter_stream_turn(int(user_message_id)):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

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