# -*- coding: utf-8 -*-
{
    "name": "HR Attendance Chatbot (LiteLLM)",
    "version": "18.0.1.2.0",
    "category": "Human Resources/Attendances",
    "summary": "Floating attendance assistant for captains and HR (LiteLLM, server-side)",
    "description": """
Captain and HR attendance officers get a floating chat in the Odoo backend.
The server calls LiteLLM on the Odoo host; the browser never sees the API key.

Configure on the server (Settings → Technical → System Parameters, or SQL):

- hr_attendance_chatbot.litellm_base_url — e.g. http://127.0.0.1:4000
- hr_attendance_chatbot.litellm_model — model name passed to LiteLLM
- hr_attendance_chatbot.litellm_api_key — optional Bearer token (server only)

Until litellm_model is set, the widget stays hidden for everyone.
    """,
    "author": "Kien Viet",
    "license": "LGPL-3",
    "depends": [
        "hr_attendance_portal",
        "web",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web/static/lib/dompurify/DOMpurify.js",
            "hr_attendance_chatbot/static/src/attendance_chat/attendance_chat.scss",
            "hr_attendance_chatbot/static/src/attendance_chat/markdown_safe.js",
            "hr_attendance_chatbot/static/src/attendance_chat/attendance_chat.xml",
            "hr_attendance_chatbot/static/src/attendance_chat/attendance_chat.js",
            "hr_attendance_chatbot/static/src/attendance_chat/attendance_chat_service.js",
        ],
    },
    "installable": True,
    "application": False,
}