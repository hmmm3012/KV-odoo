# -*- coding: utf-8 -*-

import re
import unicodedata
from datetime import timedelta
from io import BytesIO

from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare, float_is_zero, float_round, html_escape
import xlsxwriter  # Odoo 19: no longer re-exported by odoo.tools.misc

WEEKDAYS = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")
MAX_EXPORT_DAYS = 62
PROP_WORK_SHIFT = "Ca làm việc"
MOBILE_TAG_CANONICAL = "CĐCĐ"
MOBILE_TAG_ASCII = "CDCD"


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
    preview_html = fields.Html(
        string="Timesheet Preview",
        sanitize=False,
        readonly=True,
    )

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
        if values.get("department_id") and values.get("date_from") and values.get("date_to"):
            try:
                values["preview_html"] = self.new(values)._render_preview_html()
            except (AccessError, UserError):
                values["preview_html"] = False
        return values

    @api.onchange("department_id", "date_from", "date_to")
    def _onchange_timesheet_filters(self):
        self.preview_html = False
        if not (self.department_id and self.date_from and self.date_to):
            return
        if self.date_from > self.date_to:
            return
        if (self.date_to - self.date_from).days + 1 > MAX_EXPORT_DAYS:
            return
        try:
            self.preview_html = self._render_preview_html()
        except (AccessError, UserError):
            self.preview_html = False

    def action_preview(self):
        self.ensure_one()
        self.preview_html = self._render_preview_html()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
            "context": dict(self.env.context),
        }

    def action_export(self):
        self.ensure_one()
        self._check_export()
        return {
            "type": "ir.actions.act_url",
            "url": "/hr_attendance_portal/timesheet/%s" % self.id,
            "target": "download",
        }

    def action_reset_row_order(self):
        """Clear saved row order for this lot and rebuild the preview A→Z."""
        self.ensure_one()
        self._check_export()
        self._reset_row_order(self.department_id)
        self.preview_html = self._render_preview_html()
        return True

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

    @api.model
    def _check_row_order_department(self, department):
        department = department.sudo()
        if not department:
            raise UserError(self.env._("Choose the parking lot to export."))
        department.with_user(self.env.user).check_access("read")
        return department

    @api.model
    def save_row_order(self, department_id, employee_ids):
        """Persist display order for one section of a parking-lot timesheet.

        ``employee_ids`` is the section's employee list in the new top-to-bottom
        order. Other sections keep their existing ranks.
        """
        department = self._check_row_order_department(
            self.env["hr.department"].browse(int(department_id))
        )
        employee_ids = [int(employee_id) for employee_id in (employee_ids or []) if employee_id]
        if not employee_ids:
            return True
        employees = self.env["hr.employee"].browse(employee_ids).exists()
        if set(employees.ids) != set(employee_ids):
            raise UserError(self.env._("Some employees in the timesheet order no longer exist."))
        Order = self.env["hr.attendance.timesheet.row.order"]
        existing = {
            order.employee_id.id: order
            for order in Order.search([
                ("department_id", "=", department.id),
                ("employee_id", "in", employee_ids),
            ])
        }
        for index, employee_id in enumerate(employee_ids):
            sequence = (index + 1) * 10
            order = existing.get(employee_id)
            if order:
                if order.sequence != sequence:
                    order.sequence = sequence
            else:
                Order.create({
                    "department_id": department.id,
                    "employee_id": employee_id,
                    "sequence": sequence,
                })
        return True

    @api.model
    def _reset_row_order(self, department):
        department = self._check_row_order_department(department)
        self.env["hr.attendance.timesheet.row.order"].search([
            ("department_id", "=", department.id),
        ]).unlink()
        return True

    def _timesheet_row_order_map(self):
        self.ensure_one()
        orders = self.env["hr.attendance.timesheet.row.order"].search([
            ("department_id", "=", self.department_id.id),
        ])
        return {order.employee_id.id: order.sequence for order in orders}

    @api.model
    def _sort_employees_for_timesheet(self, employees, order_map):
        return employees.sorted(
            lambda employee: (
                order_map.get(employee.id, 10**9),
                (employee.name or "").casefold(),
                employee.id,
            )
        )

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

    def _timesheet_departments(self):
        """Departments that belong to the selected parking lot.

        A timesheet is always for one lot. Parent groups such as "Bãi xe" that
        contain several parking lots are rejected so support staff who worked
        one day at one lot do not inherit hours from every sibling lot.
        """
        self.ensure_one()
        department = self.department_id
        child_lots = self.env["hr.department"].search([
            ("id", "child_of", department.id),
            ("id", "!=", department.id),
            ("attendance_location_id", "!=", False),
        ])
        if child_lots:
            raise UserError(self.env._(
                "Select a specific parking lot. Combined timesheets for %(name)s "
                "are not allowed because they mix hours from %(lots)s."
            ) % {
                "name": department.display_name,
                "lots": ", ".join(child_lots.mapped("name")[:8])
                + ("…" if len(child_lots) > 8 else ""),
            })
        return self.env["hr.department"].search([("id", "child_of", department.id)])

    def _prepare_timesheet(self):
        """Build official, mobile, and support rows for the selected parking lot.

        Official staff belong to the lot's department and are not tagged CĐCĐ.
        Mobile (Cơ động) staff belong to the lot and carry the CĐCĐ tag.
        Support staff belong somewhere else and checked in at this lot.
        Day/night sections follow the employee Property "Ca làm việc"
        (missing value defaults to day). A day cell only sums hours from
        shifts that actually happened at this lot (regular + approved
        overtime). Allowance stays empty.
        """
        self.ensure_one()
        self._check_export()
        dates = []
        cursor = self.date_from
        while cursor <= self.date_to:
            dates.append(cursor)
            cursor += timedelta(days=1)

        department = self.department_id
        departments = self._timesheet_departments()
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
            employee = attendance.employee_id
            slot = buckets.setdefault(employee.id, {}).setdefault(work_date, {})
            slot["regular"] = float_round((slot.get("regular") or 0.0) + regular, precision_digits=2)
            slot["overtime"] = float_round((slot.get("overtime") or 0.0) + overtime, precision_digits=2)

        order_map = self._timesheet_row_order_map()
        official_employees = self._sort_employees_for_timesheet(
            self.env["hr.employee"].search(
                [("department_id", "in", list(department_ids))],
                order="name, id",
            ),
            order_map,
        )
        official_ids = set(official_employees.ids)
        support_employees = self._sort_employees_for_timesheet(
            self.env["hr.employee"].browse([
                employee_id for employee_id in buckets if employee_id not in official_ids
            ]),
            order_map,
        )

        def has_hours(employee):
            return any(
                (slot.get("regular") or 0.0) or (slot.get("overtime") or 0.0)
                for slot in buckets.get(employee.id, {}).values()
            )

        def rows_for(employees, kind, support=False, require_hours=False):
            people = []
            for employee in employees:
                if self._employee_work_shift_kind(employee) != kind:
                    continue
                if require_hours and not has_hours(employee):
                    continue
                people.append(
                    self._timesheet_row(
                        employee,
                        dates,
                        buckets.get(employee.id, {}),
                        kind,
                        support=support,
                    )
                )
            return people

        mobile_employees = official_employees.filtered(self._employee_is_mobile)
        roster_employees = official_employees - mobile_employees
        return {
            "department": department,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "dates": dates,
            "official_day": rows_for(roster_employees, "day"),
            "official_night": rows_for(roster_employees, "night"),
            "mobile_day": rows_for(mobile_employees, "day"),
            "mobile_night": rows_for(mobile_employees, "night"),
            "support_day": rows_for(support_employees, "day", support=True, require_hours=True),
            "support_night": rows_for(support_employees, "night", support=True, require_hours=True),
        }

    def _timesheet_attendances(self, department_ids, location_ids):
        start = fields.Datetime.to_datetime(self.date_from) - timedelta(days=1)
        end = fields.Datetime.to_datetime(self.date_to) + timedelta(days=2)
        domain = [
            ("check_in", ">=", start),
            ("check_in", "<", end),
            ("session_state", "!=", "denied"),
        ]
        # Pull punches marked at this lot, plus unmarked punches of staff who
        # belong here (legacy rows without site marks). Do not pull every
        # punch of lot staff — other lots' marked shifts must stay out.
        alternatives = [
            ("in_department_id", "in", list(department_ids)),
            ("out_department_id", "in", list(department_ids)),
        ]
        if location_ids:
            alternatives += [
                ("in_location_id", "in", list(location_ids)),
                ("out_location_id", "in", list(location_ids)),
            ]
        unmarked_home = [
            "&", "&", "&", "&",
            ("employee_id.department_id", "in", list(department_ids)),
            ("in_department_id", "=", False),
            ("out_department_id", "=", False),
            ("in_location_id", "=", False),
            ("out_location_id", "=", False),
        ]
        site = ["|"] * len(alternatives) + alternatives + unmarked_home
        attendances = self.env["hr.attendance"].search(domain + site)
        return attendances.filtered(
            lambda attendance: self._matches_site(attendance, department_ids, location_ids)
        )

    @api.model
    def _matches_site(self, attendance, department_ids, location_ids):
        """A shift belongs to the lot where it was checked in.

        Check-in department wins over location so a punch marked for lot A is
        never counted on lot B just because GPS resolved a shared/nearby
        location. Check-out marks are only used when check-in has no site.
        Fully unmarked punches still fall back to the employee's home lot for
        legacy rows.
        """
        in_department = attendance.in_department_id.id
        out_department = attendance.out_department_id.id
        in_location = attendance.in_location_id.id
        out_location = attendance.out_location_id.id

        if in_department:
            return in_department in department_ids
        if in_location:
            return in_location in location_ids
        if out_department:
            return out_department in department_ids
        if out_location:
            return out_location in location_ids

        employee_department = attendance.employee_id.department_id
        return bool(employee_department) and employee_department.id in department_ids

    @api.model
    def _timesheet_date(self, attendance):
        start, _end = attendance._session_bounds()
        if not start:
            return False
        return fields.Datetime.context_timestamp(attendance, start).date()

    @api.model
    def _fold_ascii(self, value):
        # Đ/đ do not decompose under NFKD; map them before stripping marks.
        text = (value or "").replace("Đ", "D").replace("đ", "d")
        text = unicodedata.normalize("NFKD", text)
        return "".join(char for char in text if not unicodedata.combining(char)).casefold()

    @api.model
    def _is_mobile_tag_name(self, name):
        folded = re.sub(r"[\s_-]+", "", self._fold_ascii(name))
        return folded == MOBILE_TAG_ASCII.casefold()

    @api.model
    def _mobile_category_ids(self):
        categories = self.env["hr.employee.category"].search([])
        return categories.filtered(lambda category: self._is_mobile_tag_name(category.name)).ids

    @api.model
    def _employee_is_mobile(self, employee):
        # Captains export timesheets without hr.group_hr_user; tags stay readable via sudo.
        return any(
            self._is_mobile_tag_name(category.name)
            for category in employee.sudo().category_ids
        )

    @api.model
    def _employee_work_shift_kind(self, employee):
        """Return 'day' or 'night'; an unset "Ca làm việc" counts as day."""
        return self._employee_work_shift_value(employee) or "day"

    @api.model
    def _employee_work_shift_value(self, employee):
        """Return 'day', 'night', or False from the employee Property "Ca làm việc".

        Captains may lack hr.group_hr_user, so Properties are read with sudo.
        """
        visible = employee.sudo()
        company = visible.company_id
        definitions = company.employee_properties_definition or []
        definition = next(
            (item for item in definitions if item.get("string") == PROP_WORK_SHIFT),
            None,
        )
        if not definition:
            return False
        raw = (visible.employee_properties or {}).get(definition.get("name"))
        if not raw:
            return False
        if definition.get("type") == "selection":
            options = {
                option[0]: option[1]
                for option in (definition.get("selection") or [])
                if option
            }
            label = options.get(raw) or raw
        else:
            label = raw
        folded = re.sub(r"\s+", " ", self._fold_ascii(str(label))).strip()
        if folded in ("ca dem", "night", "ca night"):
            return "night"
        return "day"

    @api.model
    def _merge_mobile_employee_tags(self):
        """Collapse CDCD / cđcd / CĐCĐ variants into one canonical CĐCĐ tag."""
        Category = self.env["hr.employee.category"].sudo()
        duplicates = Category.search([]).filtered(
            lambda category: self._is_mobile_tag_name(category.name)
        )
        if not duplicates:
            return Category.browse()
        canonical = duplicates.filtered(lambda category: category.name == MOBILE_TAG_CANONICAL)[:1]
        if not canonical:
            canonical = duplicates.sorted("id")[:1]
            conflict = Category.search([
                ("name", "=", MOBILE_TAG_CANONICAL),
                ("id", "not in", duplicates.ids),
            ], limit=1)
            if conflict:
                canonical = conflict
                duplicates |= conflict
            elif canonical.name != MOBILE_TAG_CANONICAL:
                canonical.name = MOBILE_TAG_CANONICAL
        extras = duplicates - canonical
        if extras:
            employees = self.env["hr.employee"].sudo().search([
                ("category_ids", "in", extras.ids),
            ])
            for employee in employees:
                employee.category_ids = (employee.category_ids - extras) | canonical
            extras.unlink()
        return canonical

    @api.model
    def _timesheet_hours(self, attendance):
        """Regular hours are the recognized payroll hours.

        Overtime is the payroll figure after the captain has reviewed, or the
        captain's approved hours while a legacy HR review is still open.
        """
        regular = attendance.payroll_regular_hours or 0.0
        state = attendance.overtime_state
        if state in ("captain_reviewed", "closed", "hr_discrepancy"):
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
            day_regular = slot.get("regular") or 0.0
            day_overtime = slot.get("overtime") or 0.0
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

    @api.model
    def _format_hours(self, value):
        if float_is_zero(value, precision_digits=2):
            return ""
        return ("%0.2f" % value).rstrip("0").rstrip(".")

    @api.model
    def _is_half_hour(self, value):
        """True when displayed hours end in .5 (e.g. 11.5, 12.5)."""
        if float_is_zero(value, precision_digits=2):
            return False
        rounded = float_round(value, precision_digits=2)
        fraction = abs(rounded) % 1.0
        return float_compare(fraction, 0.5, precision_digits=2) == 0

    @api.model
    def _day_cell_css(self, value):
        text = self._format_hours(value)
        css = "kv-day kv-num"
        if not text:
            css += " kv-blank"
        elif self._is_half_hour(value):
            css += " kv-half"
        return css, text

    @api.model
    def _timesheet_site_totals(self, payload):
        """Sum regular/overtime/total hours for the whole parking lot."""
        people = (
            list(payload.get("official_day") or [])
            + list(payload.get("official_night") or [])
            + list(payload.get("mobile_day") or [])
            + list(payload.get("mobile_night") or [])
            + list(payload.get("support_day") or [])
            + list(payload.get("support_night") or [])
        )
        day_count = len(payload.get("dates") or [])
        days = [0.0] * day_count
        regular = 0.0
        overtime = 0.0
        total = 0.0
        worked_days = 0
        for person in people:
            person_days = person.get("days") or []
            for index in range(day_count):
                value = person_days[index] if index < len(person_days) else 0.0
                days[index] = float_round(days[index] + value, precision_digits=2)
            regular = float_round(regular + (person.get("regular") or 0.0), precision_digits=2)
            overtime = float_round(overtime + (person.get("overtime") or 0.0), precision_digits=2)
            total = float_round(total + (person.get("total") or 0.0), precision_digits=2)
            worked_days += person.get("worked_days") or 0
        return {
            "days": days,
            "regular": regular,
            "overtime": overtime,
            "total": total,
            "worked_days": worked_days,
            "people_count": len([person for person in people if not float_is_zero(person.get("total") or 0.0, precision_digits=2)]),
        }

    def _render_preview_html(self):
        self.ensure_one()
        payload = self._prepare_timesheet()
        dates = payload["dates"]
        site_totals = self._timesheet_site_totals(payload)
        start = payload["date_from"]
        end = payload["date_to"]
        if (
            start.year == end.year
            and start.month == end.month
            and start.day == 1
            and (end + timedelta(days=1)).month != end.month
        ):
            heading = "BẢNG CHẤM CÔNG NHÂN VIÊN THÁNG %s/%s" % (start.month, start.year)
        else:
            heading = "BẢNG CHẤM CÔNG NHÂN VIÊN"
        period = "( Từ Ngày %s đến %s )" % (
            start.strftime("%d/%m/%Y"),
            end.strftime("%d/%m/%Y"),
        )
        lot = "Bãi xe: %s" % (payload["department"].name or "")
        sections = (
            ("A", "Ca Ngày", "official_day", payload["official_day"]),
            ("B", "Ca Đêm", "official_night", payload["official_night"]),
            ("C", "Cơ động Ca Ngày", "mobile_day", payload["mobile_day"]),
            ("D", "Cơ động Ca Đêm", "mobile_night", payload["mobile_night"]),
            ("E", "Đến hỗ trợ Ca Ngày", "support_day", payload["support_day"]),
            ("F", "Đến hỗ trợ Ca Đêm", "support_night", payload["support_night"]),
        )
        summary_headers = (
            "Tổng giờ",
            "Chức vụ",
            "Bãi hỗ trợ",
            "Ca",
            "Số ngày LV",
            "Giờ thường",
            "Tăng ca",
        )
        col_count = 3 + len(dates) + len(summary_headers)

        parts = [
            '<div class="kv-timesheet-wrap" data-department-id="%s">'
            % int(payload["department"].id),
            '<div class="kv-timesheet-meta">',
            "<h2>%s</h2>" % html_escape(heading),
            "<p class=\"kv-timesheet-period\">%s</p>" % html_escape(period),
            "<p class=\"kv-timesheet-lot\">%s</p>" % html_escape(lot),
            "<p class=\"kv-timesheet-hint\">Kéo biểu tượng ⋮⋮ ở cột STT để đổi thứ tự trong từng nhóm; kéo trong khung bảng để xem ngày. Ô vàng = giờ lẻ (.5).</p>",
            '<div class="kv-timesheet-toolbar">',
            '<button type="button" class="btn btn-secondary btn-sm kv-timesheet-reset-order">Đặt lại thứ tự A→Z</button>',
            '<span class="kv-timesheet-order-status" aria-live="polite"></span>',
            "</div>",
            "</div>",
            '<div class="kv-timesheet-scroll" tabindex="0">',
            '<table class="kv-timesheet">',
            "<thead>",
            "<tr>",
            '<th class="kv-sticky kv-sticky-0" rowspan="2">STT</th>',
            '<th class="kv-sticky kv-sticky-1" rowspan="2">Họ và tên</th>',
            '<th class="kv-sticky kv-sticky-2">Thứ</th>',
        ]
        for day in dates:
            parts.append(
                '<th class="kv-day">%s</th>' % html_escape(WEEKDAYS[day.weekday()])
            )
        for label in summary_headers:
            parts.append(
                '<th class="kv-summary" rowspan="2">%s</th>' % html_escape(label)
            )
        parts.extend([
            "</tr>",
            "<tr>",
            '<th class="kv-sticky kv-sticky-2">MSNV</th>',
        ])
        for day in dates:
            parts.append(
                '<th class="kv-day">%s</th>' % html_escape(day.strftime("%d"))
            )
        parts.extend(["</tr>", "</thead>", "<tbody>"])

        trailing = col_count - 3
        for letter, label, section_key, people in sections:
            parts.append('<tr class="kv-section" data-section="%s">' % html_escape(section_key))
            parts.append(
                '<td class="kv-sticky kv-sticky-0">%s</td>' % html_escape(letter)
            )
            parts.append(
                '<td class="kv-sticky kv-sticky-1">%s</td>' % html_escape(label)
            )
            parts.append('<td class="kv-sticky kv-sticky-2"></td>')
            if trailing:
                parts.append('<td colspan="%s"></td>' % trailing)
            parts.append("</tr>")
            if not people:
                parts.append('<tr class="kv-empty" data-section="%s">' % html_escape(section_key))
                parts.append('<td class="kv-sticky kv-sticky-0"></td>')
                parts.append(
                    '<td class="kv-sticky kv-sticky-1 kv-muted">Không có dữ liệu</td>'
                )
                parts.append('<td class="kv-sticky kv-sticky-2"></td>')
                if trailing:
                    parts.append('<td colspan="%s"></td>' % trailing)
                parts.append("</tr>")
                continue
            for sequence, person in enumerate(people, start=1):
                parts.append(
                    '<tr class="kv-person" data-section="%s" data-employee-id="%s">'
                    % (html_escape(section_key), int(person["employee"].id))
                )
                parts.append(
                    '<td class="kv-sticky kv-sticky-0 kv-num">'
                    '<span class="kv-drag-handle" title="Kéo để đổi thứ tự" role="button" tabindex="-1">⋮⋮</span>'
                    '<span class="kv-row-index">%s</span></td>' % sequence
                )
                parts.append(
                    '<td class="kv-sticky kv-sticky-1 kv-name">%s</td>'
                    % html_escape(person["name"])
                )
                parts.append(
                    '<td class="kv-sticky kv-sticky-2 kv-code">%s</td>'
                    % html_escape(person["code"])
                )
                for value in person["days"]:
                    css, text = self._day_cell_css(value)
                    parts.append('<td class="%s">%s</td>' % (css, html_escape(text)))
                parts.append(
                    '<td class="kv-summary kv-num kv-total">%s</td>'
                    % html_escape(self._format_hours(person["total"]))
                )
                parts.append(
                    '<td class="kv-summary kv-text">%s</td>' % html_escape(person["job"])
                )
                parts.append(
                    '<td class="kv-summary kv-text">%s</td>'
                    % html_escape(person["support_site"])
                )
                parts.append(
                    '<td class="kv-summary kv-center">%s</td>'
                    % html_escape(person["shift"])
                )
                parts.append(
                    '<td class="kv-summary kv-num">%s</td>' % person["worked_days"]
                )
                parts.append(
                    '<td class="kv-summary kv-num">%s</td>'
                    % html_escape(self._format_hours(person["regular"]))
                )
                parts.append(
                    '<td class="kv-summary kv-num">%s</td>'
                    % html_escape(self._format_hours(person["overtime"]))
                )
                parts.append("</tr>")

        parts.append('<tr class="kv-site-total">')
        parts.append('<td class="kv-sticky kv-sticky-0"></td>')
        parts.append(
            '<td class="kv-sticky kv-sticky-1">Tổng cả bãi</td>'
        )
        parts.append('<td class="kv-sticky kv-sticky-2"></td>')
        for value in site_totals["days"]:
            css, text = self._day_cell_css(value)
            parts.append('<td class="%s">%s</td>' % (css, html_escape(text)))
        parts.append(
            '<td class="kv-summary kv-num kv-total">%s</td>'
            % html_escape(self._format_hours(site_totals["total"]) or "0")
        )
        parts.append('<td class="kv-summary"></td>')
        parts.append('<td class="kv-summary"></td>')
        parts.append('<td class="kv-summary"></td>')
        parts.append('<td class="kv-summary"></td>')
        parts.append(
            '<td class="kv-summary kv-num">%s</td>'
            % html_escape(self._format_hours(site_totals["regular"]) or "0")
        )
        parts.append(
            '<td class="kv-summary kv-num">%s</td>'
            % html_escape(self._format_hours(site_totals["overtime"]) or "0")
        )
        parts.append("</tr>")

        parts.extend(["</tbody>", "</table>", "</div>", "</div>"])
        return Markup("".join(parts))

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
        hours_half = workbook.add_format(self._cell_style(
            align="center", num_format="0.##", size=12, bg="#FDE68A", bold=True,
        ))
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
        site_totals = self._timesheet_site_totals(payload)
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
            ("C", "Cơ động Ca Ngày", payload["mobile_day"]),
            ("D", "Cơ động Ca Đêm", payload["mobile_night"]),
            ("E", "Đến hỗ trợ Ca Ngày", payload["support_day"]),
            ("F", "Đến hỗ trợ Ca Đêm", payload["support_night"]),
        )
        total_row_style = workbook.add_format(self._cell_style(
            bold=True, bg="#FFF2CC", align="center", num_format="0.##", size=12,
        ))
        total_name_style = workbook.add_format(self._cell_style(
            bold=True, bg="#FFF2CC", align="left", size=12,
        ))
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
                        style = hours_half if self._is_half_hour(value) else hours
                        sheet.write_number(row, day_start + index, value, style)
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

        for col in range(last_col + 1):
            sheet.write_blank(row, col, None, total_row_style)
        sheet.write(row, 1, "Tổng cả bãi", total_name_style)
        total_half_style = workbook.add_format(self._cell_style(
            bold=True, bg="#FDE68A", align="center", num_format="0.##", size=12,
        ))
        for index, value in enumerate(site_totals["days"]):
            if float_is_zero(value, precision_digits=2):
                sheet.write_blank(row, day_start + index, None, total_row_style)
            elif self._is_half_hour(value):
                sheet.write_number(row, day_start + index, value, total_half_style)
            else:
                sheet.write_number(row, day_start + index, value, total_row_style)
        sheet.write_number(row, columns["total"], site_totals["total"], total_row_style)
        sheet.write_number(row, columns["regular"], site_totals["regular"], total_row_style)
        sheet.write_number(row, columns["hour"], site_totals["overtime"], total_row_style)

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
