# -*- coding: utf-8 -*-

import base64
from collections import defaultdict
from datetime import date
from io import BytesIO

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
import xlsxwriter  # Odoo 19: no longer re-exported by odoo.tools.misc

SHIFT_SELECTION = [("day", "Ca ngày"), ("night", "Ca đêm")]
MAX_EXPORT_DAYS = 62


class HrDepartmentOff(models.Model):
    _name = "hr.department.off"
    _description = "Lịch OFF"
    _order = "date desc, department_id, shift, employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Nhân viên",
        required=True,
        index=True,
        ondelete="cascade",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Phòng ban",
        compute="_compute_department_id",
        store=True,
        precompute=True,
        readonly=False,
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="department_id.company_id",
        store=True,
        precompute=True,
        index=True,
    )
    date = fields.Date("Ngày OFF", required=True, index=True)
    shift = fields.Selection(
        SHIFT_SELECTION,
        string="Ca",
        compute="_compute_shift",
        store=True,
        precompute=True,
        readonly=False,
        required=True,
    )
    note = fields.Char("Ghi chú")

    _employee_date_unique = models.Constraint(
        "unique(employee_id, date)",
        "Nhân viên này đã có lịch OFF trong ngày đó.",
    )

    @api.depends("employee_id")
    def _compute_department_id(self):
        for off in self:
            # department_id lives on hr.version in Odoo 19; captains may not
            # have hr.group_hr_user and cannot read version_id directly.
            employee = off.employee_id.sudo()
            if employee.department_id:
                off.department_id = employee.department_id

    @api.depends("employee_id")
    def _compute_shift(self):
        Timesheet = self.env["hr.attendance.timesheet.wizard"]
        for off in self:
            if off.employee_id:
                off.shift = Timesheet._employee_work_shift_kind(off.employee_id.sudo())
            elif not off.shift:
                off.shift = "day"

    @api.depends("employee_id", "date")
    def _compute_display_name(self):
        for off in self:
            date_label = off.date.strftime("%d/%m/%Y") if off.date else ""
            off.display_name = " - ".join(
                part for part in (off.employee_id.name, date_label) if part
            )

    @api.constrains("department_id", "date", "shift")
    def _check_off_limit(self):
        labels = dict(SHIFT_SELECTION)
        for off in self:
            department = off.department_id.sudo()
            limit = department.off_max_night if off.shift == "night" else department.off_max_day
            if not limit:
                continue
            # Serialize concurrent registrations for the same department.
            self.env.cr.execute(
                "SELECT id FROM hr_department WHERE id = %s FOR UPDATE",
                (department.id,),
            )
            count = self.sudo().search_count([
                ("department_id", "=", department.id),
                ("date", "=", off.date),
                ("shift", "=", off.shift),
            ])
            if count > limit:
                raise ValidationError(self.env._(
                    "%(department)s chỉ cho phép tối đa %(limit)s người OFF %(shift)s "
                    "trong ngày %(date)s.",
                    department=department.display_name,
                    limit=limit,
                    shift=labels[off.shift].lower(),
                    date=off.date.strftime("%d/%m/%Y"),
                ))

    @api.model_create_multi
    def create(self, vals_list):
        offs = super().create(vals_list)
        offs._check_off_month_open()
        return offs

    def write(self, vals):
        self._check_off_month_open()
        res = super().write(vals)
        if {"date", "department_id"}.intersection(vals):
            self._check_off_month_open()
        return res

    def unlink(self):
        self._check_off_month_open()
        return super().unlink()

    @api.model
    def _off_user_is_hr(self):
        user = self.env.user
        return (
            self.env.su
            or user.has_group("hr.group_hr_user")
            or user.has_group("hr_attendance.group_hr_attendance_officer")
            or user.has_group("base.group_system")
        )

    @api.model
    def _off_lock_date(self, day, company):
        """First day on which captains can no longer change the month of ``day``."""
        lock_day = min(max(company.off_schedule_lock_day or 27, 1), 28)
        return day.replace(day=1) - relativedelta(months=1) + relativedelta(day=lock_day)

    def _check_off_month_open(self):
        if self._off_user_is_hr():
            return
        today = fields.Date.context_today(self)
        for off in self:
            company = off.sudo().department_id.company_id or self.env.company
            lock_date = self._off_lock_date(off.date, company)
            if today >= lock_date:
                raise UserError(self.env._(
                    "Lịch OFF tháng %(month)s đã chốt từ ngày %(lock)s. Chỉ nhân sự được chỉnh sửa.",
                    month=off.date.strftime("%m/%Y"),
                    lock=lock_date.strftime("%d/%m/%Y"),
                ))

    @api.model
    def _off_calendar_department_domain(self):
        if self._off_user_is_hr():
            return []
        return [("id", "in", self.env.user._hr_site_captain_department_ids())]

    @api.model
    def _off_calendar_department(self, department_id):
        department = self.env["hr.department"].search(
            self._off_calendar_department_domain() + [("id", "=", int(department_id))]
        )
        if not department:
            raise AccessError(self.env._("Bạn không được nhập lịch OFF cho phòng ban này."))
        return department

    @api.model
    def _off_calendar_month(self, year, month):
        date_from = date(int(year), int(month), 1)
        return date_from, date_from + relativedelta(months=1, days=-1)

    @api.model
    def off_calendar_departments(self):
        departments = self.env["hr.department"].search(self._off_calendar_department_domain())
        # complete_name is no longer stored in Odoo 19, so it cannot be used
        # as a SQL order. Sort in Python and still display the complete name.
        departments = departments.sorted(lambda dep: (dep.complete_name or dep.name or "").casefold())
        return [{"id": department.id, "name": department.complete_name} for department in departments]

    @api.model
    def off_calendar_load(self, department_id, year, month):
        department = self._off_calendar_department(department_id)
        date_from, date_to = self._off_calendar_month(year, month)
        offs = self.search([
            ("department_id", "=", department.id),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ])
        Timesheet = self.env["hr.attendance.timesheet.wizard"]
        employees = (department.sudo().member_ids | offs.employee_id).sorted(
            lambda employee: (employee.name or "").casefold()
        )
        days = {}
        for off in offs:
            days.setdefault(fields.Date.to_string(off.date), {"day": [], "night": []})[off.shift].append(
                off.employee_id.id
            )
        lock_date = self._off_lock_date(date_from, department.company_id or self.env.company)
        today = fields.Date.context_today(self)
        return {
            "lock": {
                "date": fields.Date.to_string(lock_date),
                "last_day": fields.Date.to_string(lock_date - relativedelta(days=1)),
                "locked": today >= lock_date,
                "is_hr": bool(self._off_user_is_hr()),
            },
            "department": {"id": department.id, "name": department.complete_name},
            "year": date_from.year,
            "month": date_from.month,
            "first_weekday": date_from.weekday(),
            "days_in_month": date_to.day,
            "today": fields.Date.to_string(today),
            "limits": {"day": department.off_max_day, "night": department.off_max_night},
            "employees": [
                {
                    "id": employee.id,
                    "name": employee.name,
                    "shift": Timesheet._employee_work_shift_value(employee) or "",
                }
                for employee in employees
            ],
            "offs": days,
        }

    @api.model
    def off_calendar_save(self, department_id, year, month, offs):
        """Replace the department's OFF schedule for one month.

        ``offs`` maps ``YYYY-MM-DD`` to ``{"day": [employee ids], "night": [employee ids]}``.
        """
        department = self._off_calendar_department(department_id)
        date_from, date_to = self._off_calendar_month(year, month)
        existing = self.search([
            ("department_id", "=", department.id),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ])
        allowed_ids = set((department.sudo().member_ids | existing.employee_id).ids)
        desired = {}
        for day_key, shifts in (offs or {}).items():
            day = fields.Date.to_date(day_key)
            if not date_from <= day <= date_to:
                raise UserError(self.env._("Ngày %s không thuộc tháng đang nhập.", day_key))
            day_ids = {int(employee_id) for employee_id in (shifts or {}).get("day") or []}
            night_ids = {int(employee_id) for employee_id in (shifts or {}).get("night") or []}
            if (day_ids | night_ids) - allowed_ids:
                raise AccessError(self.env._("Chỉ được xếp OFF cho nhân viên của %s.", department.name))
            both = day_ids & night_ids
            if both:
                raise UserError(self.env._(
                    "Ngày %(date)s: %(names)s đang nằm ở cả ca ngày và ca đêm.",
                    date=day.strftime("%d/%m/%Y"),
                    names=", ".join(self.env["hr.employee"].browse(sorted(both)).mapped("name")),
                ))
            desired.update({(employee_id, day): "day" for employee_id in day_ids})
            desired.update({(employee_id, day): "night" for employee_id in night_ids})
        self._sync_department_offs(department, existing, desired)
        return self.off_calendar_load(department.id, year, month)

    @api.model
    def _sync_department_offs(self, department, existing, desired):
        """Make ``existing`` match ``desired`` ({(employee_id, date): shift})."""
        removed = existing.filtered(lambda off: (off.employee_id.id, off.date) not in desired)
        kept = existing - removed
        removed.unlink()
        for off in kept:
            shift = desired[(off.employee_id.id, off.date)]
            if off.shift != shift:
                off.shift = shift
        known = {(off.employee_id.id, off.date) for off in kept}
        missing = {key: shift for key, shift in desired.items() if key not in known}
        if not missing:
            return
        elsewhere = self.sudo().search([
            ("employee_id", "in", list({employee_id for employee_id, _day in missing})),
            ("date", "in", list({day for _employee_id, day in missing})),
            ("department_id", "!=", department.id),
        ]).filtered(lambda off: (off.employee_id.id, off.date) in missing)
        if elsewhere:
            raise UserError(self.env._(
                "Đã có lịch OFF ở phòng ban khác: %s",
                "; ".join(
                    "%s %s (%s)" % (off.employee_id.name, off.date.strftime("%d/%m"), off.department_id.name)
                    for off in elsewhere
                ),
            ))
        self.create([
            {"employee_id": employee_id, "department_id": department.id, "date": day, "shift": shift}
            for (employee_id, day), shift in sorted(missing.items(), key=lambda item: (item[0][1], item[0][0]))
        ])


class HrDepartmentOffExport(models.TransientModel):
    _name = "hr.department.off.export"
    _description = "Xuất lịch OFF"

    date_from = fields.Date("Từ ngày", required=True)
    date_to = fields.Date("Đến ngày", required=True)
    department_ids = fields.Many2many(
        "hr.department",
        string="Phòng ban",
        help="Để trống để xuất mọi phòng ban có lịch OFF trong khoảng ngày.",
    )
    file = fields.Binary("Tệp", readonly=True, attachment=False)
    file_name = fields.Char("Tên tệp", readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        first_day = fields.Date.context_today(self).replace(day=1)
        values.setdefault("date_from", first_day)
        values.setdefault("date_to", first_day + relativedelta(months=1, days=-1))
        return values

    def action_export(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(self.env._("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc."))
        if (self.date_to - self.date_from).days + 1 > MAX_EXPORT_DAYS:
            raise UserError(self.env._("Chỉ xuất tối đa %s ngày mỗi lần.", MAX_EXPORT_DAYS))
        if not xlsxwriter:
            raise UserError(self.env._("Không xuất được Excel trên máy chủ này."))
        domain = [("date", ">=", self.date_from), ("date", "<=", self.date_to)]
        if self.department_ids:
            domain.append(("department_id", "in", self.department_ids.ids))
        offs = self.env["hr.department.off"].search(domain)
        departments = self.department_ids or offs.department_id
        if not departments:
            raise UserError(self.env._("Không có lịch OFF trong khoảng ngày đã chọn."))
        departments = departments.sorted(lambda dept: (dept.name or "").casefold())
        self.write({
            "file": base64.b64encode(self._render_xlsx(departments, offs)),
            "file_name": "Lich_OFF_%s_%s.xlsx" % (
                self.date_from.strftime("%d%m%Y"),
                self.date_to.strftime("%d%m%Y"),
            ),
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content?model=%s&id=%s&field=file&filename_field=file_name&download=true"
            % (self._name, self.id),
            "target": "download",
        }

    def _render_xlsx(self, departments, offs):
        names = defaultdict(list)
        for off in offs.sorted(lambda item: (item.employee_id.name or "").casefold()):
            names[(off.date, off.department_id.id, off.shift)].append(off.employee_id.name)

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("OFF")
        base = {"font_name": "Times New Roman", "border": 1, "valign": "vcenter", "text_wrap": True}
        title = workbook.add_format({"font_name": "Times New Roman", "bold": True, "font_size": 14})
        header = workbook.add_format(dict(base, bold=True, align="center", bg_color="#92D050"))
        day_cell = workbook.add_format(dict(base, bold=True, align="center"))
        name_cell = workbook.add_format(dict(base, align="left"))
        night_cell = workbook.add_format(dict(base, align="left", bg_color="#D9D9D9"))

        last_col = len(departments) * 2
        sheet.merge_range(0, 0, 0, last_col, self.env._(
            "LỊCH OFF %(date_from)s - %(date_to)s",
            date_from=self.date_from.strftime("%d/%m/%Y"),
            date_to=self.date_to.strftime("%d/%m/%Y"),
        ), title)
        sheet.merge_range(2, 0, 3, 0, "Ngày", header)
        sheet.set_column(0, 0, 8)
        sheet.set_column(1, last_col, 16)
        for index, department in enumerate(departments):
            col = 1 + index * 2
            sheet.merge_range(2, col, 2, col + 1, department.name, header)
            sheet.write(3, col, "Ngày", header)
            sheet.write(3, col + 1, "Đêm", header)

        row = 4
        day = self.date_from
        while day <= self.date_to:
            sheet.write(row, 0, day.strftime("%d/%m"), day_cell)
            for index, department in enumerate(departments):
                col = 1 + index * 2
                sheet.write(row, col, ", ".join(names[(day, department.id, "day")]), name_cell)
                sheet.write(row, col + 1, ", ".join(names[(day, department.id, "night")]), night_cell)
            row += 1
            day += relativedelta(days=1)
        sheet.freeze_panes(4, 1)
        workbook.close()
        return output.getvalue()

