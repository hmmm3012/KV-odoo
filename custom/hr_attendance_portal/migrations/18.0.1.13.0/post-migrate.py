# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    env["hr.attendance.location"]._migrate_vertices_to_zones()
