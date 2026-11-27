# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    kpi_lock_day = fields.Integer(
        string="Ngày chốt nhập KPI",
        default=5,
        help="Đội trưởng sửa được KPI của một tháng đến hết ngày trước ngày này của tháng sau "
        "(ví dụ KPI tháng 11 chốt nhập trước ngày 05/12). Từ ngày này chỉ nhân sự được sửa.",
    )

    @api.constrains("kpi_lock_day")
    def _check_kpi_lock_day(self):
        for company in self:
            if not 1 <= company.kpi_lock_day <= 28:
                raise ValidationError(self.env._("Ngày chốt KPI phải từ 1 đến 28."))