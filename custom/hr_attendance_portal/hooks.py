# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    # Odoo 17+ (and 19) passes an Environment instead of (cr, registry).
    env["hr.attendance.location"]._migrate_vertices_to_zones()
    _logger.info("Attendance workplace fence points migrated into polygon zones.")
