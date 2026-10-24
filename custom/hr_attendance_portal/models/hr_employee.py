# -*- coding: utf-8 -*-

import base64
import hmac
import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from passlib.context import CryptContext

_logger = logging.getLogger(__name__)

PIN_CRYPT_CONTEXT = CryptContext(
    schemes=["pbkdf2_sha512"],
    deprecated="auto",
    pbkdf2_sha512__rounds=120000,
)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _attendance_captain_keeps_private_profile(self, access_uid=None):
        """Captains open the same employee form as the Employees menu.

        Stock HR sends every non-officer to hr.employee.public. A captain can
        read the private record, including a visitor who punched at their site,
        but the public profile is outside that scope.
        """
        user = self.env.user
        if access_uid:
            user = self.env["res.users"].browse(access_uid).sudo()
        return user.has_group("hr_attendance_portal.group_hr_attendance_site_captain")

    def get_formview_id(self, access_uid=None):
        if self._attendance_captain_keeps_private_profile(access_uid):
            return False
        return super().get_formview_id(access_uid=access_uid)

    def get_formview_action(self, access_uid=None):
        action = super().get_formview_action(access_uid=access_uid)
        if self._attendance_captain_keeps_private_profile(access_uid):
            action["res_model"] = "hr.employee"
            action["views"] = [(False, "form")]
        return action

    attendance_portal_enabled = fields.Boolean(
        string="Allow Portal Check-in",
        default=True,
        help="Allow this employee to check in and out from the attendance portal without an Odoo user.",
    )
    attendance_pin_hash = fields.Char(
        groups="base.group_system",
        copy=False,
    )
    attendance_pin_is_set = fields.Boolean(
        compute="_compute_attendance_pin_is_set",
        compute_sudo=True,
        string="Attendance PIN Set",
    )
    attendance_location_ids = fields.Many2many(
        "hr.attendance.location",
        "hr_attendance_location_employee_rel",
        "employee_id",
        "location_id",
        string="Portal Workplaces",
        help="Workplaces this employee may use. Assigned on the workplace form.",
    )
    attendance_face_image = fields.Image(
        string="Enrolled Face",
        max_width=512,
        max_height=512,
        help="Frontal selfie used for attendance face recognition. Do not use a studio ID portrait.",
    )
    attendance_face_embedding = fields.Binary(
        string="Face Embedding",
        attachment=False,
        copy=False,
        groups="base.group_system",
    )
    attendance_face_enrolled_at = fields.Datetime(
        string="Face Enrolled At",
        readonly=True,
        copy=False,
    )
    attendance_face_is_enrolled = fields.Boolean(
        compute="_compute_attendance_face_is_enrolled",
        compute_sudo=True,
        string="Face Enrolled",
    )

    @api.depends("pin", "attendance_pin_hash")
    def _compute_attendance_pin_is_set(self):
        for employee in self:
            employee.attendance_pin_is_set = bool(employee.sudo().attendance_pin_hash or employee.pin)

    @api.depends("attendance_face_embedding", "attendance_face_enrolled_at")
    def _compute_attendance_face_is_enrolled(self):
        for employee in self:
            employee.attendance_face_is_enrolled = bool(employee.sudo().attendance_face_embedding)

    @api.model
    def _attendance_pin_crypt_context(self):
        return PIN_CRYPT_CONTEXT

    @api.model
    def _hash_attendance_pin(self, pin):
        return self._attendance_pin_crypt_context().hash(pin)

    @api.model
    def _dummy_attendance_pin_hash(self):
        icp = self.env["ir.config_parameter"].sudo()
        hashed = icp.get_param("hr_attendance_portal.dummy_pin_hash")
        if not hashed:
            hashed = self._hash_attendance_pin("00000000")
            icp.set_param("hr_attendance_portal.dummy_pin_hash", hashed)
        return hashed

    def _store_attendance_pin_hash(self, pin):
        hashed = self._hash_attendance_pin(pin) if pin else False
        self.with_context(skip_attendance_pin_hash=True).sudo().write({
            "attendance_pin_hash": hashed,
        })

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        for employee, vals in zip(employees, vals_list):
            pin = vals.get("pin")
            if pin:
                employee._store_attendance_pin_hash(pin)
            if vals.get("attendance_face_image"):
                employee._enroll_attendance_face(vals.get("attendance_face_image"))
        employees._apply_auto_attendance_setup(sync_face=True)
        return employees

    def write(self, vals):
        res = super().write(vals)
        if "attendance_face_image" in vals and not self.env.context.get("skip_attendance_face_embed"):
            lenient = self.env.context.get("attendance_face_enroll_lenient")
            for employee in self:
                employee._enroll_attendance_face(
                    vals.get("attendance_face_image"),
                    raise_on_error=not lenient,
                )
        if not self.env.context.get("skip_attendance_pin_hash") and "pin" in vals:
            pin = vals.get("pin")
            for employee in self:
                employee._store_attendance_pin_hash(pin)
                self.env["hr.attendance.session"].sudo()._revoke_employee(employee)
        watched = {"department_id", "image_1920", "emp_code"}
        if not self.env.context.get("skip_auto_attendance") and watched.intersection(vals):
            self._apply_auto_attendance_setup(
                sync_face="image_1920" in vals or "department_id" in vals,
            )
        return res

    @api.model
    def _attendance_pin_from_emp_code(self, emp_code):
        """Last five digits of the employee code, padded when the code is shorter."""
        digits = "".join(char for char in (emp_code or "") if char.isdigit())
        if not digits:
            return False
        return digits[-5:].zfill(5)

    def _apply_auto_attendance_setup(self, sync_face=False):
        """Set the attendance PIN from the employee code and enroll the HR photo.

        A photo that cannot be enrolled does not block saving the employee.
        An attendance PIN already stored on the employee is left unchanged.
        """
        if self.env.context.get("skip_auto_attendance"):
            return
        for employee in self:
            if not employee.pin:
                pin = employee._attendance_pin_from_emp_code(employee.emp_code)
                if pin:
                    employee.with_context(skip_auto_attendance=True).write({"pin": pin})
            if not sync_face:
                continue
            photo = employee.with_context(bin_size=False).image_1920
            if not photo:
                continue
            employee.with_context(
                skip_auto_attendance=True,
                attendance_face_enroll_lenient=True,
            ).write({"attendance_face_image": photo})

    def _enroll_attendance_face(self, raw=None, raise_on_error=True):
        """Detect, align, and store a 1:1 embedding from the enrolled selfie."""
        self.ensure_one()
        if raw is None:
            raw = self.with_context(bin_size=False).attendance_face_image
        if not raw:
            self.with_context(skip_attendance_face_embed=True).sudo().write({
                "attendance_face_embedding": False,
                "attendance_face_enrolled_at": False,
            })
            return True
        from .face_detection import unwrap_image_bytes
        from .face_pipeline import packing_embedding, process_face

        data = unwrap_image_bytes(raw)

        result = process_face(data)
        if result.get("unavailable"):
            message = self.env._(
                "Face recognition is unavailable. Install OpenCV and the SFace model."
            )
            return self._attendance_face_enroll_failed(message, raise_on_error)
        reason = result.get("quality_reason") or False
        if reason:
            message = self.env._(self._attendance_face_enroll_error(reason))
            return self._attendance_face_enroll_failed(message, raise_on_error)
        embedding = result.get("embedding")
        if not embedding:
            message = self.env._("Could not compute a face embedding from this photo.")
            return self._attendance_face_enroll_failed(message, raise_on_error)
        self.with_context(skip_attendance_face_embed=True).sudo().write({
            "attendance_face_embedding": packing_embedding(embedding),
            "attendance_face_enrolled_at": fields.Datetime.now(),
        })
        return True

    def _attendance_face_enroll_failed(self, message, raise_on_error):
        self.with_context(skip_attendance_face_embed=True).sudo().write({
            "attendance_face_embedding": False,
            "attendance_face_enrolled_at": False,
        })
        if raise_on_error:
            raise ValidationError(message)
        _logger.warning(
            "Attendance face was not enrolled for employee %s: %s",
            self.id,
            message,
        )
        if not self.env.context.get("attendance_face_enroll_quiet"):
            self.message_post(body=message)
        return False

    @api.model
    def _attendance_face_enroll_error(self, reason):
        return {
            "no_face": "No face found. Upload a clear frontal selfie taken on a phone, not a studio portrait.",
            "multiple_faces": "The photo shows more than one face. Upload a selfie with only this employee.",
            "face_too_small": "The face is too small. Upload a closer frontal selfie.",
            "face_tilted": "The face is tilted. Upload a photo with the head upright.",
            "face_turned": "The face is turned. Upload a photo looking straight at the camera.",
            "face_check_unavailable": "Face recognition is unavailable. Install OpenCV and the SFace model.",
        }.get(reason, "The photo is not usable for attendance face enrollment.")

    def action_register_attendance_face(self):
        for employee in self:
            if not employee.attendance_face_image:
                raise ValidationError(self.env._(
                    "Upload a frontal selfie before registering the face."
                ))
            employee._enroll_attendance_face()
        return True

    def _attendance_portal_verify_pin(self, pin):
        """Constant-time PIN verification. Never logs or returns the PIN."""
        self.ensure_one()
        submitted = pin or ""
        hashed = self.sudo().attendance_pin_hash
        if hashed:
            try:
                valid, new_hash = self._attendance_pin_crypt_context().verify_and_update(
                    submitted, hashed
                )
            except (ValueError, TypeError):
                valid, new_hash = False, None
            if valid and new_hash:
                self.with_context(skip_attendance_pin_hash=True).sudo().write({
                    "attendance_pin_hash": new_hash,
                })
            return bool(valid)

        stored = self.sudo().pin or ""
        if stored and hmac.compare_digest(stored, submitted):
            self._store_attendance_pin_hash(submitted)
            return True
        self._attendance_portal_dummy_verify(submitted)
        return False

    @api.model
    def _attendance_portal_dummy_verify(self, pin):
        try:
            self._attendance_pin_crypt_context().verify(pin or "", self._dummy_attendance_pin_hash())
        except (ValueError, TypeError):
            pass
        return False

    def _attendance_portal_eligible(self):
        self.ensure_one()
        if not self.active:
            return False, "inactive_employee"
        if not self.attendance_portal_enabled:
            return False, "not_eligible"
        if self.departure_date and self.departure_date <= fields.Date.context_today(self):
            return False, "not_eligible"
        if not (self.sudo().attendance_pin_hash or self.sudo().pin):
            return False, "pin_not_set"
        return True, False

    @api.model
    def _attendance_portal_find_by_code(self, employee_code):
        code = (employee_code or "").strip()
        if not code:
            return self.browse()
        domain_code = [("emp_code", "=", code)]
        employee = self.search(domain_code, limit=2)
        if len(employee) == 1:
            return employee
        if len(employee) > 1:
            return self.browse()
        employee = self.search([("barcode", "=", code)], limit=2)
        if len(employee) == 1:
            return employee
        return self.browse()

    def _attendance_action_change(self, geo_information=None):
        """Mark the stock check-in/out write as the original punch.

        Later edits of those timestamps are rejected. The portal and kiosk
        both go through this method.
        """
        return super(
            HrEmployee, self.with_context(attendance_original_punch=True)
        )._attendance_action_change(geo_information)
