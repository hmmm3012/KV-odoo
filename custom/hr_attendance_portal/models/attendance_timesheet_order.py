# -*- coding: utf-8 -*-

from odoo import fields, models


class HrAttendanceTimesheetRowOrder(models.Model):
    _name = "hr.attendance.timesheet.row.order"
    _description = "Timesheet Row Order"
    _order = "sequence, id"

    department_id = fields.Many2one(
        "hr.department",
        string="Parking Lot",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Sequence", default=10, required=True)

    _sql_constraints = [
        (
            "department_employee_uniq",
            "unique(department_id, employee_id)",
            "Each employee can only have one timesheet row order per parking lot.",
        ),
    ]
