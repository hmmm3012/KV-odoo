# -*- coding: utf-8 -*-

import re
from datetime import timedelta
from io import BytesIO

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_round
from odoo.tools.misc import xlsxwriter

WEEKDAYS = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")
MAX_EXPORT_DAYS = 62


class HrAttendanceTimesheetWizard(models.TransientModel):
    _name = "hr.attendance.timesheet.wizard"
    _description = "Attendance Timesheet"

    department_id = fields.Many2one(
        "hr.department",
        string="Parking Lot",
        required=True,
        domain=lambda self: self._department_domain(),
    )
    date_from = fields.Date(string="Date From", required=True)
    date_to = fields.Date(string="Date To", required=True)

    @api.model
    def _department_domain(self):
        user = self.env.user
        if user.has_group("hr_attendance.group_hr_attendance_officer") or user.has_group("base.group_system"):
            return []
        return [("id", "in", user._hr_site_captain_department_ids())]

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        values.setdefault("date_from", today.replace(day=1))
        values.setdefault("date_to", today)
        if "department_id" in fields_list and not values.get("department_id"):
            department_ids = self.env.user._hr_site_captain_department_ids()
            departments = self.env["hr.department"].browse(department_ids).exists()
            roots = departments.filtered(lambda dept: not dept.parent_id or dept.parent_id not in departments)
            if len(roots) == 1:
                values["department_id"] = roots.id
        return values

    def action_export(self):
        self.ensure_one()
        self._check_export()
        return {
            "type": "ir.actions.act_url",
            "url": "/hr_attendance_portal/timesheet/%s" % self.id,
            "target": "download",
        }

    def _check_export(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(self.env._("Choose the dates to export."))
        if self.date_from > self.date_to:
            raise UserError(self.env._("The start date must be on or before the end date."))
        if (self.date_to - self.date_from).days + 1 > MAX_EXPORT_DAYS:
            raise UserError(self.env._("Export at most %s days at a time.", MAX_EXPORT_DAYS))
        department = self.sudo().department_id
        if not department:
            raise UserError(self.env._("Choose the parking lot to export."))
        department.with_user(self.env.user).check_access("read")

    def _filename(self):
        self.ensure_one()
        start, end = self.date_from, self.date_to
        if (
            start.year == end.year
            and start.month == end.month
            and start.day == 1
            and (end + timedelta(days=1)).month != end.month
        ):
            period = "T%s.%s" % (start.month, start.year)
        else:
            period = "%s-%s" % (start.strftime("%d%m%Y"), end.strftime("%d%m%Y"))
        label = re.sub(r"\s+", " ", re.sub(r"[^\w .\-()]+", " ", self.department_id.name or "")).strip()
        return "BCC %s%s.xlsx" % (period, (" " + label) if label else "")

    def _prepare_timesheet(self):
        """Build official and support rows for the selected parking lot.

        Official staff belong to the lot's department. Support staff belong
        somewhere else and checked in or out at this lot. A day cell is the
        sum of regular hours and approved overtime. Allowance stays empty.
        """
        self.ensure_one()
        self._check_export()
        dates = []
        cursor = self.date_from
        while cursor <= self.date_to:
            dates.append(cursor)
            cursor += timedelta(days=1)

        department = self.department_id
        departments = self.env["hr.department"].search([("id", "child_of", department.id)])
        department_ids = set(departments.ids)
        location_ids = set(departments.mapped("attendance_location_id").ids)
        buckets = {}
        for attendance in self._timesheet_attendances(department_ids, location_ids):
            regular, overtime = self._timesheet_hours(attendance)
            if float_is_zero(regular, precision_digits=2) and float_is_zero(overtime, precision_digits=2):
                continue
            work_date = self._timesheet_date(attendance)
            if not work_date or work_date < self.date_from or work_date > self.date_to:
                continue
            kind = "night" if self._is_night_shift(attendance) else "day"
            employee = attendance.employee_id
            slot = buckets.setdefault(employee.id, {}).setdefault(work_date, {})
            slot["%s_regular" % kind] = float_round((slot.get("%s_regular" % kind) or 0.0) + regular, precision_digits=2)
            slot["%s_overtime" % kind] = float_round((slot.get("%s_overtime" % kind) or 0.0) + overtime, precision_digits=2)

        official_employees = self.env["hr.employee"].search(
            [("department_id", "in", list(department_ids))],
            order="name, id",
        )
        official_ids = set(official_employees.ids)
        support_employees = self.env["hr.employee"].browse([
            employee_id for employee_id in buckets if employee_id not in official_ids
        ]).sorted(lambda employee: ((employee.name or "").casefold(), employee.id))

        def has_hours(employee, kind):
            return any(
                (slot.get("%s_regular" % kind) or 0.0) or (slot.get("%s_overtime" % kind) or 0.0)
                for slot in buckets.get(employee.id, {}).values()
            )

        official_day = official_employees.filtered(
            lambda employee: has_hours(employee, "day") or not (has_hours(employee, "day") or has_hours(employee, "night"))
        )
        return {
            "department": department,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "dates": dates,
            "official_day": [self._timesheet_row(employee, dates, buckets.get(employee.id, {}), "day") for employee in official_day],
            "official_night": [self._timesheet_row(employee, dates, buckets.get(employee.id, {}), "night") for employee in official_employees if has_hours(employee, "night")],
            "support_day": [self._timesheet_row(employee, dates, buckets.get(employee.id, {}), "day", support=True) for employee in support_employees if has_hours(employee, "day")],
            "support_night": [self._timesheet_row(employee, dates, buckets.get(employee.id, {}), "night", support=True) for employee in support_employees if has_hours(employee, "night")],
        }

    def _timesheet_attendances(self, department_ids, location_ids):
        start = fields.Datetime.to_datetime(self.date_from) - timedelta(days=1)
        end = fields.Datetime.to_datetime(self.date_to) + timedelta(days=2)
        domain = [
            ("check_in", ">=", start),
            ("check_in", "<", end),
            ("session_state", "!=", "denied"),
        ]
        site = [
            "|", "|",
            ("employee_id.department_id", "in", list(department_ids)),
            ("in_department_id", "in", list(department_ids)),
            ("out_department_id", "in", list(department_ids)),
        ]
        if location_ids:
            site = ["|", "|"] + site + [
                ("in_location_id", "in", list(location_ids)),
                ("out_location_id", "in", list(location_ids)),
            ]
        attendances = self.env["hr.attendance"].search(domain + site)
        return attendances.filtered(
            lambda attendance: self._matches_site(attendance, department_ids, location_ids)
        )

    @api.model
    def _matches_site(self, attendance, department_ids, location_ids):
        department_marks = {attendance.in_department_id.id, attendance.out_department_id.id} - {False}
        location_marks = {attendance.in_location_id.id, attendance.out_location_id.id} - {False}
        if department_marks & department_ids or location_marks & location_ids:
            return True
        employee_department = attendance.employee_id.department_id
        return bool(employee_department) and employee_department.id in department_ids and not department_marks and not location_marks

    @api.model
    def _timesheet_date(self, attendance):
        start, _end = attendance._session_bounds()
        if not start:
            return False
        return fields.Datetime.context_timestamp(attendance, start).date()

    @api.model
    def _is_night_shift(self, attendance):
        """A shift that starts from 18:00 through before 06:00 is the night section."""
        start, _end = attendance._session_bounds()
        if not start:
            return False
        hour = fields.Datetime.context_timestamp(attendance, start).hour
        return hour >= 18 or hour < 6

    @api.model
    def _timesheet_hours(self, attendance):
        """Regular hours are the recognized payroll hours.

        Overtime is the payroll figure after HR review, or the captain's
        approved hours while that review is still open.
        """
        regular = attendance.payroll_regular_hours or 0.0
        state = attendance.overtime_state
        if state in ("hr_reviewed", "closed", "hr_discrepancy"):
            overtime = attendance.payroll_overtime_hours or 0.0
        elif state == "pending_hr_review":
            overtime = attendance.captain_approved_hours or 0.0
        else:
            overtime = 0.0
        return (
            float_round(regular, precision_digits=2),
            float_round(overtime, precision_digits=2),
        )

    @api.model
    def _timesheet_row(self, employee, dates, by_date, kind, support=False):
        days = []
        regular = 0.0
        overtime = 0.0
        worked_days = 0
        for day in dates:
            slot = by_date.get(day) or {}
            day_regular = slot.get("%s_regular" % kind) or 0.0
            day_overtime = slot.get("%s_overtime" % kind) or 0.0
            total = float_round(day_regular + day_overtime, precision_digits=2)
            regular = float_round(regular + day_regular, precision_digits=2)
            overtime = float_round(overtime + day_overtime, precision_digits=2)
            if not float_is_zero(total, precision_digits=2):
                worked_days += 1
            days.append(total)
        visible = employee.sudo()
        job = visible.job_id.name or ""
        support_site = (visible.department_id.name or "") if support else ""
        return {
            "employee": employee,
            "name": employee.name or "",
            "code": (employee.emp_code or "") if "emp_code" in employee._fields else "",
            "job": job,
            "support_site": support_site,
            "shift": "Ca Đêm" if kind == "night" else "Ca Ngày",
            "days": days,
            "total": float_round(regular + overtime, precision_digits=2),
            "regular": regular,
            "overtime": overtime,
            "worked_days": worked_days,
        }

    def _render_xlsx(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(self.env._("Excel export is not available."))
        payload = self._prepare_timesheet()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet_name = re.sub(r"[:\\/?*\[\]]", " ", payload["department"].name or "Bảng công").strip()[:31] or "Bảng công"
        sheet = workbook.add_worksheet(sheet_name)
        self._write_timesheet(workbook, sheet, payload)
        workbook.close()
        output.seek(0)
        return output.getvalue()

    def _write_timesheet(self, workbook, sheet, payload):
        dates = payload["dates"]
        day_start = 3
        day_end = day_start + len(dates) - 1
        columns = {
            "total": day_end + 1,
            "sign": day_end + 2,
            "role": day_end + 3,
            "note": day_end + 4,
            "site": day_end + 5,
            "shift": day_end + 6,
            "worked": day_end + 7,
            "regular": day_end + 8,
            "rest": day_end + 9,
            "day13": day_end + 10,
            "hour": day_end + 11,
            "holiday": day_end + 12,
            "tet": day_end + 13,
            "lot_review": day_end + 14,
            "hr_review": day_end + 15,
        }
        last_col = columns["hr_review"]
        title = workbook.add_format({
            "font_name": "Times New Roman", "bold": True, "font_size": 16,
            "align": "center", "valign": "vcenter",
        })
        subtitle = workbook.add_format({
            "font_name": "Times New Roman", "bold": True, "font_size": 14,
            "align": "center", "valign": "vcenter", "font_color": "#0070C0",
        })
        lot = workbook.add_format({
            "font_name": "Times New Roman", "bold": True, "font_size": 16,
            "align": "left", "valign": "vcenter", "font_color": "#0070C0",
        })
        banner = workbook.add_format({
            "font_name": "Times New Roman", "bold": True, "font_size": 11,
            "align": "center", "valign": "vcenter", "font_color": "#0070C0",
        })
        header = workbook.add_format(self._cell_style(bold=True, bg="#92D050", align="center", text_wrap=True, size=11))
        header_small = workbook.add_format(self._cell_style(bold=True, bg="#92D050", align="center", size=8))
        date_header = workbook.add_format(self._cell_style(bold=True, bg="#92D050", align="center", num_format="dd", size=11))
        section = workbook.add_format(self._cell_style(bold=True, bg="#D9EAD3", align="center", size=12))
        section_name = workbook.add_format(self._cell_style(bold=True, bg="#D9EAD3", align="left", size=12))
        name = workbook.add_format(self._cell_style(bold=True, align="left", size=12))
        center = workbook.add_format(self._cell_style(align="center", size=11))
        text = workbook.add_format(self._cell_style(align="left", size=11))
        hours = workbook.add_format(self._cell_style(align="center", num_format="0.##", size=12))
        integer = workbook.add_format(self._cell_style(align="center", num_format="0", size=12))

        start = payload["date_from"]
        end = payload["date_to"]
        if start.year == end.year and start.month == end.month and start.day == 1 and (end + timedelta(days=1)).month != end.month:
            heading = "BẢNG CHẤM CÔNG NHÂN VIÊN THÁNG %s/%s" % (start.month, start.year)
        else:
            heading = "BẢNG CHẤM CÔNG NHÂN VIÊN"
        sheet.merge_range(0, 0, 0, last_col, heading, title)
        sheet.merge_range(1, 0, 1, last_col, "( Từ Ngày %s đến %s )" % (
            start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y"),
        ), subtitle)
        sheet.merge_range(2, 0, 2, last_col, "Bãi xe: %s" % (payload["department"].name or ""), lot)
        sheet.merge_range(3, 0, 3, columns["sign"], "Phần in ra cho Nhân viên ký xác nhận", banner)
        sheet.merge_range(3, columns["role"], 3, columns["shift"], "Phần nhập của Quản lý Bãi xe", banner)
        sheet.merge_range(3, columns["worked"], 3, last_col, "Phần nhập của Phòng HCNS", banner)
        sheet.set_row(0, 22)
        sheet.set_row(1, 20)
        sheet.set_row(2, 22)
        sheet.set_row(4, 22)
        sheet.set_row(5, 48)

        sheet.merge_range(4, 0, 5, 0, "STT", header)
        sheet.merge_range(4, 1, 5, 1, "HỌ VÀ TÊN", header)
        sheet.write(4, 2, "Thứ", header)
        sheet.write(5, 2, "MSNV", header)
        for index, day in enumerate(dates):
            col = day_start + index
            sheet.write(4, col, WEEKDAYS[day.weekday()], header_small)
            sheet.write_datetime(5, col, fields.Date.to_date(day), date_header)
        sheet.merge_range(4, columns["total"], 5, columns["total"], "Tổng giờ Công", header)
        sheet.merge_range(4, columns["sign"], 5, columns["sign"], "NV Ký Xác nhận", header)
        sheet.merge_range(4, columns["role"], 4, columns["shift"], "Thông tin Tham chiếu", header)
        sheet.write(5, columns["role"], "Đối tượng / Chức vụ", header)
        sheet.write(5, columns["note"], "Ghi chú Phụ Cấp", header)
        sheet.write(5, columns["site"], "Bãi xe\n(chỉ ghi khi có NV đến hỗ trợ)", header)
        sheet.write(5, columns["shift"], "Ca làm việc", header)
        sheet.merge_range(4, columns["worked"], 4, columns["tet"], "Giờ công (h)", header)
        sheet.write(5, columns["worked"], "Tổng số ngày\nLàm việc trong tháng", header)
        sheet.write(5, columns["regular"], "Giờ công thường\n1.0", header)
        sheet.write(5, columns["rest"], "Số ngày tăng ca ngày nghỉ", header)
        sheet.write(5, columns["day13"], "Tăng ca\nngày 1.3", header)
        sheet.write(5, columns["hour"], "Tăng ca\ngiờ 1.5", header)
        sheet.write(5, columns["holiday"], "Tăng ca\nLễ 2.0", header)
        sheet.write(5, columns["tet"], "Tăng ca\ntết 3.0", header)
        sheet.merge_range(4, columns["lot_review"], 4, columns["hr_review"], "Đánh giá", header)
        sheet.write(5, columns["lot_review"], "Bãi xe\nĐánh giá", header)
        sheet.write(5, columns["hr_review"], "P. Nhân sự\nđánh giá", header)

        sheet.set_column(0, 0, 6)
        sheet.set_column(1, 1, 32)
        sheet.set_column(2, 2, 14)
        sheet.set_column(day_start, day_end, 6)
        sheet.set_column(columns["total"], last_col, 14)
        sheet.freeze_panes(6, 3)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(4, 5)
        sheet.set_paper(9)

        sections = (
            ("A", "Ca Ngày", payload["official_day"]),
            ("B", "Ca Đêm", payload["official_night"]),
            ("C", "Đến hỗ trợ Ca Ngày", payload["support_day"]),
            ("D", "Đến hỗ trợ Ca Đêm", payload["support_night"]),
        )
        row = 6
        for letter, label, people in sections:
            for col in range(last_col + 1):
                sheet.write_blank(row, col, None, section)
            sheet.write(row, 0, letter, section)
            sheet.write(row, 1, label, section_name)
            row += 1
            for sequence, person in enumerate(people, start=1):
                sheet.write_number(row, 0, sequence, center)
                sheet.write(row, 1, person["name"], name)
                sheet.write(row, 2, person["code"], center)
                for index, value in enumerate(person["days"]):
                    if float_is_zero(value, precision_digits=2):
                        sheet.write_blank(row, day_start + index, None, hours)
                    else:
                        sheet.write_number(row, day_start + index, value, hours)
                sheet.write_number(row, columns["total"], person["total"], hours)
                sheet.write_blank(row, columns["sign"], None, center)
                sheet.write(row, columns["role"], person["job"], text)
                sheet.write_blank(row, columns["note"], None, text)
                sheet.write(row, columns["site"], person["support_site"], text)
                sheet.write(row, columns["shift"], person["shift"], center)
                sheet.write_number(row, columns["worked"], person["worked_days"], integer)
                sheet.write_number(row, columns["regular"], person["regular"], hours)
                for key in ("rest", "day13", "holiday", "tet", "lot_review", "hr_review"):
                    sheet.write_blank(row, columns[key], None, center)
                sheet.write_number(row, columns["hour"], person["overtime"], hours)
                row += 1

    @api.model
    def _cell_style(self, bold=False, bg=None, align="center", font_color="#000000", text_wrap=False, num_format=None, size=11):
        style = {
            "font_name": "Times New Roman",
            "font_size": size,
            "bold": bold,
            "align": align,
            "valign": "vcenter",
            "font_color": font_color,
            "border": 1,
            "text_wrap": text_wrap,
        }
        if bg:
            style["bg_color"] = bg
        if num_format:
            style["num_format"] = num_format
        return style
