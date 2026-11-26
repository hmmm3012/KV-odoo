{
    "name": "KV HR Contract",
    "version": "19.0.1.2.0",
    "license": "LGPL-3",
    "description": "A Custom Module for HR Contracts (Odoo 19: contracts live on hr.version)",
    "summary": "A Custom Module for HR Contracts",
    "category": "Human Resources",
    # Odoo 19 merged hr_contract into hr: hr.contract became hr.version.
    "depends": ["hr"],
    "author": "Hoang Minh",
    "data": [
        "views/kv_hr_contract_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
