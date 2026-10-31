# -*- coding: utf-8 -*-

from werkzeug.exceptions import NotFound

from odoo.http import Controller, content_disposition, request, route


class AttendanceTimesheetController(Controller):
    @route("/hr_attendance_portal/timesheet/<int:wizard_id>", type="http", auth="user")
    def timesheet(self, wizard_id, **kwargs):
        wizard = request.env["hr.attendance.timesheet.wizard"].browse(wizard_id).exists()
        if not wizard:
            raise NotFound()
        content = wizard._render_xlsx()
        return request.make_response(content, headers=[
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(wizard._filename())),
        ])
