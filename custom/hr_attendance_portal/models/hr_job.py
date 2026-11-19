# -*- coding: utf-8 -*-

from odoo import fields, models


class HrJob(models.Model):
    _inherit = "hr.job"

    structure_role = fields.Selection(
        [("qlbx", "QLBX"), ("cskh", "CSKH")],
        string="Nhóm cơ cấu",
        help="Nhóm của chức vụ trong cơ cấu nhân sự phòng ban. "
        "Để trống thì nhân viên được đếm theo \"Ca làm việc\" (ca ngày / ca đêm).",
    )
