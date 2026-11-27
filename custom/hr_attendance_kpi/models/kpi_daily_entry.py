# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrKpiDailyEntry(models.TransientModel):
    _name = "hr.kpi.daily.entry"
    _description = "Ghi một lỗi KPI trong ngày"

    sheet_id = fields.Many2one(
        "hr.kpi.monthly.sheet",
        string="Bảng tháng",
        required=True,
        ondelete="cascade",
    )
    date = fields.Date(required=True)
    department_id = fields.Many2one(related="sheet_id.department_id")
    employee_id = fields.Many2one(
        "hr.employee",
        string="Nhân viên",
        required=True,
        domain="[('department_id', 'child_of', department_id)]",
    )
    criterion_id = fields.Many2one(
        "hr.kpi.criterion",
        string="Tiêu chí",
        required=True,
        domain=lambda self: self.env["hr.kpi.criterion"]._daily_criteria_domain(),
    )
    note = fields.Char(string="Ghi chú")
    daily_line_id = fields.Many2one(
        "hr.kpi.daily.line",
        string="Dòng KPI",
        help="Khi sửa một lần ghi đã có.",
    )

    @api.model
    def _day_list_action(self, sheet, day):
        view = self.env.ref("hr_attendance_kpi.view_hr_kpi_daily_day_entries_list")
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("KPI ngày %s", day.strftime("%d/%m/%Y")),
            "res_model": "hr.kpi.daily.line",
            "view_mode": "list",
            "views": [(view.id, "list")],
            "domain": [
                ("sheet_id", "=", sheet.id),
                ("date", "=", day),
                ("is_fail", "=", True),
            ],
            "target": "new",
            "context": {
                "kpi_sheet_id": sheet.id,
                "kpi_hub_date": fields.Date.to_string(day),
                "default_date": fields.Date.to_string(day),
                "default_is_fail": True,
            },
        }

    @api.model
    def action_open_new(self, sheet, day):
        sheet._check_captain_editable()
        sheet._ensure_employee_lines()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Thêm lỗi KPI"),
            "res_model": self._name,
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_sheet_id": sheet.id,
                "default_date": fields.Date.to_string(day),
            },
        }

    @api.model
    def action_open_edit(self, daily_line):
        daily_line.ensure_one()
        daily_line.monthly_employee_id.sheet_id._check_captain_editable()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Sửa lỗi KPI"),
            "res_model": self._name,
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_sheet_id": daily_line.sheet_id.id,
                "default_date": fields.Date.to_string(daily_line.date),
                "default_employee_id": daily_line.employee_id.id,
                "default_criterion_id": daily_line.criterion_id.id,
                "default_note": daily_line.note,
                "default_daily_line_id": daily_line.id,
            },
        }

    def _get_or_create_monthly_employee(self):
        self.ensure_one()
        if self.employee_id not in self.sheet_id.department_id.member_ids:
            raise UserError(self.env._("Nhân viên không thuộc bãi xe đã chọn."))
        line = self.sheet_id.employee_ids.filtered(
            lambda l: l.employee_id == self.employee_id
        )
        if not line:
            line = self.env["hr.kpi.monthly.employee"].create({
                "sheet_id": self.sheet_id.id,
                "employee_id": self.employee_id.id,
            })
        else:
            line = line[0]
        return line

    def _save_line(self):
        self.ensure_one()
        self.sheet_id._check_captain_editable()
        monthly = self._get_or_create_monthly_employee()
        Daily = self.env["hr.kpi.daily.line"]
        if self.daily_line_id:
            line = self.daily_line_id
            if (
                line.monthly_employee_id != monthly
                or line.criterion_id != self.criterion_id
                or line.date != self.date
            ):
                clash = Daily.search([
                    ("monthly_employee_id", "=", monthly.id),
                    ("date", "=", self.date),
                    ("criterion_id", "=", self.criterion_id.id),
                    ("id", "!=", line.id),
                ], limit=1)
                if clash:
                    raise UserError(
                        self.env._("Đã có dòng KPI cho tiêu chí này trong ngày đó.")
                    )
                line.write({
                    "monthly_employee_id": monthly.id,
                    "date": self.date,
                    "criterion_id": self.criterion_id.id,
                    "is_fail": True,
                    "note": self.note,
                })
            else:
                line.write({"is_fail": True, "note": self.note})
            return line

        line = Daily.search([
            ("monthly_employee_id", "=", monthly.id),
            ("date", "=", self.date),
            ("criterion_id", "=", self.criterion_id.id),
        ], limit=1)
        vals = {"is_fail": True, "note": self.note}
        if line:
            line.write(vals)
        else:
            line = Daily.create({
                "monthly_employee_id": monthly.id,
                "date": self.date,
                "criterion_id": self.criterion_id.id,
                **vals,
            })
        return line

    def action_save(self):
        self.ensure_one()
        self._save_line()
        return self._day_list_action(self.sheet_id, self.date)

    def action_save_and_add(self):
        self.ensure_one()
        sheet = self.sheet_id
        day = self.date
        self._save_line()
        action = self.action_open_new(sheet, day)
        action["name"] = self.env._("Thêm lỗi KPI")
        return action