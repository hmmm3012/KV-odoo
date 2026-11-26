# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models
from odoo.exceptions import UserError

# Short code, then folded full names used on the parking-lot department or workplace.
SITE_ALIASES = {
    "SRCS": ("srcs", "sunrise city south"),
    "SGP": ("sgp", "sai gon pearl", "saigon pearl"),
}

ALLOWANCE_TYPES = [
    ("co", "PC CO"),
    ("gate_out", "PC ngồi cổng ra"),
    ("gate_in", "PC ngồi cổng vào"),
    ("gate_both", "PC ngồi cổng ra/vào"),
    ("sidewalk", "PC vỉa hè"),
]

# Types that exist only at one workplace. Others are available at every lot.
TYPE_SITE = {
    "gate_both": "SRCS",
    "sidewalk": "SGP",
}

TYPE_LABELS = dict(ALLOWANCE_TYPES)


class HrAttendanceDailyAllowance(models.Model):
    _name = "hr.attendance.daily.allowance"
    _description = "Daily Site Allowance"
    _order = "date desc, employee_id, id"
    _rec_name = "employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Nhân viên",
        required=True,
        ondelete="cascade",
        index=True,
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Bãi xe",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        related="department_id.company_id",
        store=True,
        index=True,
    )
    date = fields.Date(string="Ngày", required=True, index=True)
    allowance_type = fields.Selection(
        ALLOWANCE_TYPES,
        string="Phụ cấp",
        required=True,
    )

    _sql_constraints = [
        (
            "employee_site_day_uniq",
            "unique(employee_id, department_id, date)",
            "Each employee can only have one allowance per parking lot per day.",
        ),
    ]

    @api.model
    def _workplace_codes(self, department):
        """Return {'SRCS'} / {'SGP'} when this lot is that workplace."""
        department = department.sudo()
        names = [department.name or ""]
        if department.attendance_location_id:
            names.append(department.attendance_location_id.name or "")
        fold = self.env["hr.attendance.timesheet.wizard"]._fold_ascii
        tokens = set()
        blobs = []
        for name in names:
            folded = re.sub(r"[^a-z0-9]+", " ", fold(name)).strip()
            blobs.append(folded)
            tokens.update(folded.split())
        codes = set()
        for code, aliases in SITE_ALIASES.items():
            short, phrases = aliases[0], aliases[1:]
            if short in tokens or any(phrase in blob for blob in blobs for phrase in phrases):
                codes.add(code)
        return codes

    @api.model
    def _allowed_type_keys(self, department):
        codes = self._workplace_codes(department)
        return [
            key for key, _label in ALLOWANCE_TYPES
            if TYPE_SITE.get(key) in (None, *codes)
        ]

    @api.model
    def _check_type_for_department(self, allowance_type, department):
        if allowance_type not in TYPE_LABELS:
            raise UserError(self.env._("Chọn một loại phụ cấp."))
        required = TYPE_SITE.get(allowance_type)
        if required and required not in self._workplace_codes(department):
            if required == "SRCS":
                raise UserError(self.env._("PC ngồi cổng ra/vào chỉ dùng ở bãi SRCS."))
            raise UserError(self.env._("PC vỉa hè chỉ dùng ở bãi SGP."))
        return allowance_type

    @api.constrains("allowance_type", "department_id")
    def _constrain_type_for_department(self):
        for record in self:
            record._check_type_for_department(record.allowance_type, record.department_id)
