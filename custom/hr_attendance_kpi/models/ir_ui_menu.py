# -*- coding: utf-8 -*-

from odoo import api, models, tools


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    @tools.ormcache("frozenset(self.env.user.groups_id.ids)", "debug")
    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug=debug)
        if self.env.user._is_attendance_captain_only():
            menu = self.env.ref("hr_attendance_kpi.menu_hr_kpi_hub", raise_if_not_found=False)
            if menu:
                visible.add(menu.id)
        return visible