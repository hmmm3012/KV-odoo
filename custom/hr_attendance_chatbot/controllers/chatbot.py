# -*- coding: utf-8 -*-

import json

import odoo
from odoo import api, http
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

        # The HTTP transaction cursor closes before Werkzeug drains the iterable;
        # open a dedicated cursor for the whole SSE response instead.
        dbname = request.db
        uid = request.env.uid
        ctx = dict(request.env.context)
        try:
            msg_id = int(user_message_id)
        except (TypeError, ValueError):
            return request.make_response(
                "Invalid user_message_id",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=400,
            )

        def generate():
            registry = odoo.modules.registry.Registry(dbname)
            with registry.cursor() as cr:
                env = api.Environment(cr, uid, ctx)
                chatbot = env["hr.attendance.chatbot"]
                try:
                    for event in chatbot.iter_stream_turn(msg_id):
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    cr.commit()
                except Exception as exc:
                    cr.rollback()
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