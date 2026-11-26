# -*- coding: utf-8 -*-

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