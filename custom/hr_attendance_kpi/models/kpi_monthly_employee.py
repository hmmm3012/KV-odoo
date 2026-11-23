# -*- coding: utf-8 -*-

from odoo import api, fields, models

GROUP_FIELDS = {
    "A": ("manual_a_percent", "manual_a_note"),
    "B": ("manual_b_percent", "manual_b_note"),
    "C": "group_c_percent",
    "D": "group_d_percent",
    "E": "group_e_percent",
    "F": "group_f_percent",
}

GROUP_ROLLUP_FIELDS = {
    "A": "group_a_percent",
    "B": "group_b_percent",
    "C": "group_c_percent",
    "D": "group_d_percent",
    "E": "group_e_percent",
    "F": "group_f_percent",
}


class HrKpiMonthlyEmployee(models.Model):
    _name = "hr.kpi.monthly.employee"
    _description = "KPI tháng theo nhân viên"
    _order = "sheet_id, employee_id"

    sheet_id = fields.Many2one(
        "hr.kpi.monthly.sheet",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="cascade")
    department_id = fields.Many2one(related="sheet_id.department_id", store=True)
    company_id = fields.Many2one(related="sheet_id.company_id", store=True)
    month_date = fields.Date(related="sheet_id.month_date", store=True)
    sheet_state = fields.Selection(related="sheet_id.state", store=True)

    manual_a_percent = fields.Float(
        string="A — % trừ (nhập tay tháng)",
        help="Bổ sung ngoài tick KPI ngày; dùng cho case mô tả riêng trên tổng hợp tháng.",
    )
    manual_a_note = fields.Text(string="A — Mô tả")
    manual_b_percent = fields.Float(
        string="B — % trừ (nhập tay tháng)",
        help="Bổ sung ngoài tick KPI ngày; dùng cho case mô tả riêng trên tổng hợp tháng.",
    )
    manual_b_note = fields.Text(string="B — Mô tả")
    group_a_percent = fields.Float(string="A — % từ KPI ngày", readonly=True)
    group_b_percent = fields.Float(string="B — % từ KPI ngày", readonly=True)
    group_c_percent = fields.Float(string="C — % trừ", readonly=True)
    group_d_percent = fields.Float(string="D — % trừ", readonly=True)
    group_e_percent = fields.Float(string="E — % trừ", readonly=True)
    group_f_percent = fields.Float(string="F — % trừ", readonly=True)
    total_deduction_percent = fields.Float(string="Tổng % trừ", readonly=True)
    kpi_remaining_percent = fields.Float(string="Còn lại %", readonly=True)
    note = fields.Char(string="Ghi chú")

    daily_line_ids = fields.One2many("hr.kpi.daily.line", "monthly_employee_id", string="Chi tiết ngày")

    _sql_constraints = [
        (
            "employee_sheet_uniq",
            "unique(sheet_id, employee_id)",
            "Nhân viên đã có dòng KPI trong bảng tháng này.",
        ),
    ]

    def _check_sheet_editable(self):
        for line in self:
            line.sheet_id._check_captain_editable()
            line.sheet_id._check_department_access()

    def write(self, vals):
        manual_fields = {"manual_a_percent", "manual_a_note", "manual_b_percent", "manual_b_note", "note"}
        if manual_fields.intersection(vals) and not self.env["hr.kpi.monthly.sheet"]._user_is_hr():
            self._check_sheet_editable()
        res = super().write(vals)
        if manual_fields.intersection(vals):
            self.action_recompute()
        return res

    def action_recompute(self):
        Daily = self.env["hr.kpi.daily.line"]
        for line in self:
            grouped_hits = {}
            for daily in Daily.search([("monthly_employee_id", "=", line.id), ("is_fail", "=", True)]):
                criterion = daily.criterion_id
                grouped_hits.setdefault(criterion.id, 0)
                grouped_hits[criterion.id] += 1

            group_totals = {key: 0.0 for key in "ABCDEF"}
            criteria = self.env["hr.kpi.criterion"].search([
                ("id", "in", list(grouped_hits.keys())),
            ])
            for criterion in criteria:
                hits = grouped_hits.get(criterion.id, 0)
                group_code = criterion.group_code
                if group_code in group_totals:
                    group_totals[group_code] += criterion._deduction_for_hits(hits)

            values = {field: group_totals[code] for code, field in GROUP_ROLLUP_FIELDS.items()}
            total = sum([
                line.manual_a_percent or 0.0,
                line.manual_b_percent or 0.0,
                *values.values(),
            ])
            total = min(total, 100.0)
            values["total_deduction_percent"] = total
            values["kpi_remaining_percent"] = max(0.0, 100.0 - total)
            line.write(values)
        return True

    def action_open_daily_lines(self):
        self.ensure_one()
        self.sheet_id._check_captain_editable()
        self.sheet_id._check_department_access()
        self.env["hr.kpi.daily.wizard"]._sync_daily_lines(self)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("KPI ngày — %s", self.employee_id.name),
            "res_model": "hr.kpi.daily.line",
            "view_mode": "list",
            "domain": [("monthly_employee_id", "=", self.id)],
            "context": {
                "default_monthly_employee_id": self.id,
                "kpi_month_date": fields.Date.to_string(self.month_date),
            },
        }