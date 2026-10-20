# -*- coding: utf-8 -*-

from odoo import api, models, tools


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    @tools.ormcache("frozenset(self.env.user.groups_id.ids)", "debug")
    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug=debug)
        user = self.env.user
        if not user._is_attendance_captain_only():
            return visible
        xmlids = (
            "hr_attendance.menu_hr_attendance_root",
            "hr_attendance_portal.menu_site_captain_attendance",
            "hr_attendance_portal.menu_site_captain_session",
            "hr_attendance_portal.menu_site_captain_exception",
            "hr_attendance_portal.menu_site_captain_event",
            "hr.menu_hr_root",
            "hr.menu_hr_employee_payroll",
            "hr.menu_hr_employee_user",
        )
        allowed = set()
        for xmlid in xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                allowed.add(menu.id)
        return visible & allowed

    @api.model
    def _sync_valid_attendance_label(self):
        """Keep the Vietnamese label after the English source string changes.

        Module upgrades do not overwrite an existing translation, so the old
        name would stay on screen.
        """
        label = "Lượt hợp lệ"
        for xmlid in (
            "hr_attendance_portal.menu_site_captain_attendance",
            "hr_attendance_portal.action_site_captain_attendance",
        ):
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                record.with_context(lang="vi_VN").write({"name": label})

    @api.model
    def _sync_session_vietnamese_labels(self):
        """Fill Vietnamese labels that a normal upgrade leaves in English."""
        field_labels = {
            "hr_attendance_portal.field_hr_attendance__work_status": "Làm việc",
            "hr_attendance_portal.field_hr_attendance__recognized_regular_hours": "Giờ được công nhận",
            "hr_attendance_portal.field_hr_attendance__session_state": "Trạng thái ca",
            "hr_attendance_portal.field_hr_attendance__exception_code": "Ngoại lệ",
            "hr_attendance_portal.field_hr_attendance__raw_elapsed_hours": "Tổng giờ thô",
            "hr_attendance_portal.field_hr_attendance__standard_hours": "Giờ chuẩn",
            "hr_attendance_portal.field_hr_attendance__overtime_candidate_hours": "Overtime đề xuất",
            "hr_attendance_portal.field_hr_attendance__overtime_state": "Trạng thái overtime",
            "hr_attendance_portal.field_hr_attendance__payroll_regular_hours": "Giờ công tính lương",
            "hr_attendance_portal.field_hr_attendance__payroll_overtime_hours": "Overtime tính lương",
            "hr_attendance_portal.field_hr_attendance__effective_check_in": "Giờ vào hiệu lực",
            "hr_attendance_portal.field_hr_attendance__effective_check_out": "Giờ ra hiệu lực",
        }
        selection_labels = {
            "hr_attendance_portal.selection__hr_attendance__session_state__active": "Đang mở",
            "hr_attendance_portal.selection__hr_attendance__session_state__pending_review": "Cần xử lý",
            "hr_attendance_portal.selection__hr_attendance__session_state__validated": "Hợp lệ",
            "hr_attendance_portal.selection__hr_attendance__session_state__denied": "Từ chối",
            "hr_attendance_portal.selection__hr_attendance__session_state__modification_pending": "Chờ điều chỉnh",
            "hr_attendance_portal.selection__hr_attendance__session_state__corrected": "Đã điều chỉnh",
            "hr_attendance_portal.selection__hr_attendance__session_state__closed": "Đã chốt",
            "hr_attendance_portal.selection__hr_attendance__exception_code__none": "Không",
            "hr_attendance_portal.selection__hr_attendance__exception_code__missing_checkout": "Quên giờ ra",
            "hr_attendance_portal.selection__hr_attendance__exception_code__excessive_duration": "Vượt giờ chuẩn",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__not_required": "Không có",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__pending_captain": "Chờ đội trưởng",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__pending_hr_review": "Chờ HR",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__captain_rejected": "Đội trưởng từ chối",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__hr_reviewed": "HR đã đối chiếu",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__hr_discrepancy": "HR thấy lệch",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__closed": "Đã chốt",
            "hr_attendance_portal.selection__hr_attendance__work_status__at_work": "Đang làm việc",
            "hr_attendance_portal.selection__hr_attendance__work_status__finished": "Đã kết thúc",
        }
        for xmlid, label in field_labels.items():
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                record.with_context(lang="vi_VN").write({"field_description": label})
        for xmlid, label in selection_labels.items():
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                record.with_context(lang="vi_VN").write({"name": label})
