# -*- coding: utf-8 -*-
{
    "name": "HR Attendance Portal",
    "version": "18.0.1.8.7",
    "category": "Human Resources/Attendances",
    "summary": "PIN-based attendance portal for employees without Odoo user accounts",
    "description": """
Personal-device and shared-kiosk attendance on Odoo 18 Community.

Employees authenticate with employee code + PIN. Attendance is stored on
the standard hr.attendance model. GPS, workplace geofences, and punch-photo face presence are validated
for personal devices. Punch photos are 1:1 verified against an enrolled face
(YuNet + SFace). The standard kiosk is reused for shared devices and
routed through the same business logic.
    """,
    "author": "Kien Viet",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_attendance",
        "hr_employee_kv",
        "hr_department_access",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/attendance_location_views.xml",
        "views/attendance_device_views.xml",
        "views/attendance_event_views.xml",
        "views/hr_attendance_views.xml",
        "views/attendance_session_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_department_views.xml",
        "views/res_config_settings_views.xml",
        "views/attendance_portal_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_attendance_portal/static/src/punch_photo_field.js",
            "hr_attendance_portal/static/src/punch_photo_field.xml",
            "hr_attendance_portal/static/src/punch_photo_field.css",
        ],
    },
    "installable": True,
    "application": False,
}
