# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError

KPI_GROUPS = [
    ("A", "A — An toàn"),
    ("B", "B — Kỹ năng nghiệp vụ"),
    ("C", "C — Đồng phục / tác phong"),
    ("D", "D — Nội quy công ty"),
    ("E", "E — Vi phạm nghiêm trọng"),
    ("F", "F — Khác"),
]

DEDUCTION_TYPES = [
    ("manual", "Nhập tay (A/B)"),
    ("fixed_once", "Cố định khi có lỗi"),
    ("per_hit", "Theo số lần lỗi"),
    ("tiered", "Bậc theo số lần"),
]


class HrKpiCriterion(models.Model):
    _name = "hr.kpi.criterion"
    _description = "Tiêu chí KPI"
    _order = "group_code, sequence, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    group_code = fields.Selection(KPI_GROUPS, string="Nhóm", required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    deduction_type = fields.Selection(DEDUCTION_TYPES, required=True, default="per_hit")
    fixed_percent = fields.Float(
        string="Phần trăm trừ cố định",
        help="Dùng với loại cố định hoặc bậc.",
    )
    per_hit_percent = fields.Float(string="% mỗi lỗi")
    tier_threshold = fields.Integer(
        string="Ngưỡng bậc",
        default=3,
        help="Số lần lỗi để áp dụng phần trăm bậc cao.",
    )
    tier1_percent = fields.Float(string="% bậc 1 (mỗi lỗi)")
    tier2_percent = fields.Float(string="% bậc 2 (tổng khi vượt ngưỡng)")
    cap_percent = fields.Float(
        string="Trần % nhóm",
        help="Giới hạn phần trăm trừ tối đa cho tiêu chí này.",
    )

    _sql_constraints = [
        ("code_company_uniq", "unique(code, company_id)", "Mã tiêu chí phải duy nhất trong công ty."),
    ]

    @api.constrains("deduction_type", "group_code")
    def _check_manual_groups(self):
        for criterion in self:
            if criterion.group_code in ("A", "B") and criterion.deduction_type != "manual":
                raise ValidationError(self.env._("Nhóm A và B chỉ dùng nhập tay trên tổng hợp tháng."))
            if criterion.group_code not in ("A", "B") and criterion.deduction_type == "manual":
                raise ValidationError(self.env._("Tiêu chí nhóm C–F không dùng nhập tay."))

    @api.model
    def _daily_criteria_domain(self):
        return [
            ("active", "=", True),
            ("deduction_type", "!=", "manual"),
            ("company_id", "in", self.env.companies.ids),
        ]

    def _deduction_for_hits(self, hit_count):
        """Return deduction percent for ``hit_count`` fail days in the month."""
        self.ensure_one()
        if hit_count <= 0:
            return 0.0
        deduction = 0.0
        if self.deduction_type == "fixed_once":
            deduction = self.fixed_percent or 0.0
        elif self.deduction_type == "per_hit":
            deduction = hit_count * (self.per_hit_percent or 0.0)
        elif self.deduction_type == "tiered":
            threshold = self.tier_threshold or 3
            if hit_count >= threshold:
                deduction = self.tier2_percent or 0.0
            else:
                deduction = hit_count * (self.tier1_percent or self.per_hit_percent or 0.0)
        if self.cap_percent:
            deduction = min(deduction, self.cap_percent)
        return deduction