# -*- coding: utf-8 -*-

import base64
import csv
import io
import re
from collections import OrderedDict

from odoo import fields, models
from odoo.exceptions import UserError, ValidationError


_WKT_POLYGON = re.compile(
    r"^\s*POLYGON\s*\(\s*\((.+)\)\s*\)\s*$",
    re.IGNORECASE | re.DOTALL,
)


class HrAttendanceLocationImportWizard(models.TransientModel):
    _name = "hr.attendance.location.import.wizard"
    _description = "Import Workplace Fences from CSV"

    data_file = fields.Binary(string="CSV file", required=True)
    filename = fields.Char(string="Filename")
    result_log = fields.Text(string="Result", readonly=True)

    def action_import(self):
        self.ensure_one()
        if not self.data_file:
            raise UserError(self.env._("Upload a CSV file first."))
        try:
            raw = base64.b64decode(self.data_file)
        except (TypeError, ValueError) as error:
            raise UserError(self.env._("The uploaded file is not valid.")) from error
        text = self._decode_csv(raw)
        rows = self._read_rows(text)
        if not rows:
            raise UserError(self.env._("The CSV has no data rows."))

        company = self.env.company
        grouped = OrderedDict()
        skipped = []

        for row_number, row in enumerate(rows, start=2):
            name = (row.get("name") or "").strip()
            wkt = (row.get("wkt") or "").strip()
            description = (row.get("description") or "").strip()
            if not name:
                skipped.append(self.env._("Row %(row)s: missing name.", row=row_number))
                continue
            if not wkt:
                skipped.append(self.env._(
                    "Row %(row)s (%(name)s): missing WKT polygon.",
                    row=row_number,
                    name=name,
                ))
                continue
            try:
                points = self._parse_wkt_polygon(wkt)
            except ValidationError as error:
                skipped.append(self.env._(
                    "Row %(row)s (%(name)s): %(error)s",
                    row=row_number,
                    name=name,
                    error=error.args[0],
                ))
                continue
            grouped.setdefault(name, [])
            zone_index = len(grouped[name]) + 1
            grouped[name].append({
                "name": description or self.env._("Zone %(n)s", n=zone_index),
                "points": [
                    {"latitude": latitude, "longitude": longitude}
                    for latitude, longitude in points
                ],
                "row": row_number,
            })

        updated = []
        created = []
        linked = []

        for name, zones in grouped.items():
            departments = self._find_departments(name, company)
            location = False
            created_now = False
            first_point = zones[0]["points"][0]

            if departments:
                location = departments.mapped("attendance_location_id")[:1]
                if not location:
                    location = self._find_workplace(name, company)
                if not location:
                    location = self.env["hr.attendance.location"].create({
                        "name": name,
                        "latitude": first_point["latitude"],
                        "longitude": first_point["longitude"],
                        "allowed_radius_meters": 150,
                        "company_id": company.id,
                    })
                    created_now = True
                for department in departments.filtered(lambda dept: dept.attendance_location_id != location):
                    department.attendance_location_id = location
                    linked.append("%s → %s" % (department.name, location.name))
            else:
                location = self._find_workplace(name, company)
                if not location:
                    skipped.append(self.env._(
                        "Name %(name)s: no department or workplace with this name.",
                        name=name,
                    ))
                    continue

            try:
                location._set_fence_zones(zones)
            except ValidationError as error:
                skipped.append(self.env._(
                    "Name %(name)s: %(error)s",
                    name=name,
                    error=error.args[0],
                ))
                continue

            label = "%s (%s zone(s))" % (location.name, len(zones))
            if created_now:
                created.append(label)
            else:
                updated.append(label)

        lines = []
        if updated:
            lines.append(self.env._("Updated (%(count)s): %(names)s", count=len(updated), names=", ".join(updated)))
        if created:
            lines.append(self.env._("Created (%(count)s): %(names)s", count=len(created), names=", ".join(created)))
        if linked:
            lines.append(self.env._("Linked departments: %(names)s", names="; ".join(linked)))
        if skipped:
            lines.append(self.env._("Skipped (%(count)s):", count=len(skipped)))
            lines.extend(skipped)
        if not lines:
            lines.append(self.env._("Nothing to import."))
        self.result_log = "\n".join(lines)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _decode_csv(self, raw):
        for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise UserError(self.env._("Could not read the CSV encoding."))

    def _read_rows(self, text):
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        if not reader.fieldnames:
            raise UserError(self.env._("The CSV has no header row."))
        normalized = {
            (name or "").strip().casefold(): name
            for name in reader.fieldnames
        }
        if "name" not in normalized:
            raise UserError(self.env._('CSV must include a "name" column.'))
        if "wkt" not in normalized:
            raise UserError(self.env._('CSV must include a "WKT" column.'))
        rows = []
        for raw_row in reader:
            rows.append({
                key.strip().casefold() if key else key: (value or "").strip()
                for key, value in raw_row.items()
            })
        return rows

    def _parse_wkt_polygon(self, wkt):
        match = _WKT_POLYGON.match(wkt.strip().strip('"'))
        if not match:
            raise ValidationError(self.env._(
                "WKT must look like POLYGON ((lon lat, lon lat, ...))."
            ))
        points = []
        for token in match.group(1).split(","):
            parts = token.strip().split()
            if len(parts) != 2:
                raise ValidationError(self.env._(
                    "Each WKT point must be longitude then latitude."
                ))
            try:
                longitude = float(parts[0])
                latitude = float(parts[1])
            except ValueError as error:
                raise ValidationError(self.env._(
                    "Each WKT point must be longitude then latitude."
                )) from error
            points.append((latitude, longitude))
        return self.env["hr.attendance.location"]._normalize_fence_points(points)

    def _norm_name(self, name):
        return (name or "").strip().casefold()

    def _find_departments(self, name, company):
        target = self._norm_name(name)
        departments = self.env["hr.department"].search([
            ("company_id", "in", [company.id, False]),
            ("active", "=", True),
        ])
        return departments.filtered(lambda dept: self._norm_name(dept.name) == target)

    def _find_workplace(self, name, company):
        target = self._norm_name(name)
        locations = self.env["hr.attendance.location"].search([
            ("company_id", "=", company.id),
        ])
        matches = locations.filtered(lambda location: self._norm_name(location.name) == target)
        return matches[:1]
