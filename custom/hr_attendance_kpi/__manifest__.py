# -*- coding: utf-8 -*-
{
    "name": "HR Attendance KPI",
    "version": "18.0.1.1.3",
    "category": "Human Resources/Attendances",
    "summary": "Parking-lot employee KPI: daily entry, monthly rollup, HR lock",
    "author": "Kien Viet",
    "license": "LGPL-3",
    "depends": [
        "hr_attendance",
        "hr_attendance_portal",
        "hr_employee_kv",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/kpi_criterion_data.xml",
        "views/kpi_criterion_views.xml",
        "views/kpi_monthly_views.xml",
        "views/kpi_daily_views.xml",
        "views/kpi_hub_views.xml",
        "views/res_config_settings_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
}