# -*- coding: utf-8 -*-

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

JOB_STRUCTURE_ROLES = {
    "trưởng điều hành": "qlbx",
    "đội trưởng": "qlbx",
    "chăm sóc khách hàng": "cskh",
}


def migrate(cr, version):
    """Preset the staffing-structure group of known job positions."""
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    jobs = env["hr.job"].search([("structure_role", "=", False)])
    for job in jobs:
        names = {job.name, job.with_context(lang="vi_VN").name}
        role = next(
            (JOB_STRUCTURE_ROLES[key] for key in ((name or "").strip().casefold() for name in names)
             if key in JOB_STRUCTURE_ROLES),
            False,
        )
        if role:
            job.structure_role = role
            _logger.info("Job %s (id=%s) counted as %s in staffing structure.", job.name, job.id, role)
