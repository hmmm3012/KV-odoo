# -*- coding: utf-8 -*-

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Merge CDCD / cđcd employee tags into the canonical CĐCĐ tag."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    canonical = env["hr.attendance.timesheet.wizard"]._merge_mobile_employee_tags()
    if canonical:
        _logger.info(
            "Merged mobile employee tags into %s (id=%s).",
            canonical.name,
            canonical.id,
        )
    else:
        _logger.info("No mobile employee tags found to merge.")
