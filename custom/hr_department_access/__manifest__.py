# -*- coding: utf-8 -*-
{
    "name": "HR Department Access",
    "version": "19.0.1.0.1",
    "category": "Human Resources",
    "summary": "Limit an HR user to selected departments and their sub-departments",
    "description": """
Settings administrators can assign departments to a user. When the list is
set, that user only sees and edits employees, attendance, and contracts (hr.version) in
those departments and their sub-departments. An empty list keeps company-wide
access. The limit also applies to HR and attendance administrators.
    """,
    "author": "Kien Viet",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_attendance",
    ],
    "data": [
        "views/res_users_views.xml",
    ],
    "installable": True,
    "application": False,
}
