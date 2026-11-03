# -*- coding: utf-8 -*-
{
    "name": "HR Employee Kien Viet",
    "version": "18.0.1.3.7",
    "summary": "Adds custom fields to Employees",
    "depends": ["hr"],
    "data": [
        "security/ir.model.access.csv",
        "data/hr_employee_sequence.xml",
        "data/intro_letter_cleanup.xml",
        "views/res_company_views.xml",
        "views/intro_letter_wizard_views.xml",
        "views/hr_employee_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_employee_kv/static/src/employee_thumbs.css",
        ],
    },
    "external_dependencies": {
        "python": ["PIL", "reportlab", "pdfrw"],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
