# -*- coding: utf-8 -*-

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["hr.attendance.location"]._migrate_vertices_to_zones()
    _logger.info("Attendance workplace fence points migrated into polygon zones.")
