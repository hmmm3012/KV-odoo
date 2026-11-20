# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    kpi_lock_day = fields.Integer(
        related="company_id.kpi_lock_day",
        readonly=False,
    )