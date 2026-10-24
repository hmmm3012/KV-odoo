# -*- coding: utf-8 -*-
{
    "name": "HR Employee Kien Viet",
    "version": "18.0.1.2.2",
    "summary": "Adds custom fields to Employees",
    "depends": ["hr"],
    "data": [
        "data/hr_employee_sequence.xml",
        "views/res_company_views.xml",
        "views/hr_employee_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_employee_kv/static/src/employee_thumbs.css",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}