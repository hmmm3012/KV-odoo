{
    "name": "KV HR Contract",
    "version": "0.1",
    "license": "LGPL-3",
    "description": "A Custom Module for HR Contracts",
    "summary": "A Custom Module for HR Contracts",
    "category": "Human Resources",
    "depends": ["hr_contract", "base"],
    "author": "Hoang Minh",
    "data": [
        # XML files containing your views, actions, menus, etc.
        "views/kv_hr_contract_views.xml",
        # "report/report.xml",
    ],

    "installable": True,
    "application": False,
    "auto_install": False,
}
