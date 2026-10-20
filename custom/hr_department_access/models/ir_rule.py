# -*- coding: utf-8 -*-

from odoo import models
from odoo.osv import expression


class IrRule(models.Model):
    _inherit = "ir.rule"

    def _compute_domain(self, model_name, mode="read"):
        """AND department scope into record rules.

        Applied in Python, not as a group rule, so an Attendance or Contract
        Administrator domain of [(1, '=', 1)] cannot OR this restriction away.
        sudo() keeps the previous behavior for portal punches and crons.
        """
        domain = super()._compute_domain(model_name, mode)
        if self.env.su:
            return domain
        extra = self.env["res.users"]._hr_department_access_domain(model_name)
        if not extra:
            return domain
        return expression.AND([domain, extra])
