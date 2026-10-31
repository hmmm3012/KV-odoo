# -*- coding: utf-8 -*-

from odoo import api, models, tools


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    @tools.ormcache("frozenset(self.env.user.groups_id.ids)", "debug")
    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug=debug)
        user = self.env.user
        if user._is_attendance_hr_menu():
            root = self.env.ref("hr_attendance.menu_hr_attendance_root", raise_if_not_found=False)
            allowed_xmlids = (
                "hr_attendance.menu_hr_attendance_view_attendances",
                "hr_attendance_portal.menu_hr_overtime_to_approve",
                "hr_attendance_portal.menu_hr_attendance_timesheet",
                "hr_attendance_portal.menu_hr_attendance_event",
                "hr_attendance_portal.menu_hr_overtime_approved",
                "hr_attendance.menu_hr_attendance_reporting",
            )
            allowed = set()
            for xmlid in allowed_xmlids:
                menu = self.env.ref(xmlid, raise_if_not_found=False)
                if menu:
                    allowed.add(menu.id)
            if root:
                children = self.sudo().with_context(**{"ir.ui.menu.full_list": True}).search([
                    ("parent_id", "=", root.id),
                ])
                visible -= set(children.ids) - allowed
            return visible
        if not user._is_attendance_captain_only():
            return visible
        xmlids = (
            "hr_attendance.menu_hr_attendance_root",
            "hr_attendance_portal.menu_site_captain_attendance",
            "hr_attendance_portal.menu_site_captain_session",
            "hr_attendance_portal.menu_hr_attendance_timesheet",
            "hr_attendance_portal.menu_site_captain_exception",
            "hr_attendance_portal.menu_hr_overtime_approved",
            "hr_attendance_portal.menu_site_captain_event",
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
        labels = {
            "hr_attendance_portal.menu_site_captain_attendance": "Lượt hợp lệ",
            "hr_attendance_portal.action_site_captain_attendance": "Lượt hợp lệ",
            "hr_attendance_portal.menu_site_captain_exception": "Cần xác minh",
            "hr_attendance_portal.action_site_captain_exception": "Cần xác minh",
            "hr_attendance_portal.menu_site_captain_session": "Ca cần xử lý",
            "hr_attendance_portal.action_site_captain_session": "Ca cần xử lý",
            "hr_attendance_portal.menu_hr_attendance_timesheet": "Bảng công",
            "hr_attendance_portal.action_hr_attendance_timesheet": "Bảng công",
            "hr_attendance_portal.menu_hr_overtime_to_approve": "Cần xử lý",
            "hr_attendance_portal.action_hr_overtime_to_approve": "Cần xử lý",
            "hr_attendance_portal.menu_hr_attendance_event": "Cần xác minh",
            "hr_attendance_portal.action_hr_attendance_event": "Cần xác minh",
            "hr_attendance_portal.menu_hr_overtime_approved": "Đã duyệt",
            "hr_attendance_portal.action_hr_overtime_approved": "Đã duyệt",
        }
        for xmlid, label in labels.items():
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
            "hr_attendance_portal.field_hr_attendance__overtime_candidate_hours": "Giờ làm thêm đề xuất",
            "hr_attendance_portal.field_hr_attendance__overtime_state": "Trạng thái làm thêm",
            "hr_attendance_portal.field_hr_attendance__payroll_regular_hours": "Giờ công tính lương",
            "hr_attendance_portal.field_hr_attendance__payroll_overtime_hours": "Giờ làm thêm tính lương",
            "hr_attendance_portal.field_hr_attendance__captain_approved_hours": "Giờ đội trưởng duyệt",
            "hr_attendance_portal.field_hr_attendance__captain_overtime_reason": "Lý do đội trưởng",
            "hr_attendance_portal.field_hr_attendance__captain_approved_at": "Đội trưởng duyệt lúc",
            "hr_attendance_portal.field_hr_attendance__hr_reviewed_at": "Nhân sự đối chiếu lúc",
            "hr_attendance_portal.field_hr_attendance__approved_list_status": "Trạng thái",
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
            "hr_attendance_portal.selection__hr_attendance__overtime_state__pending_hr_review": "Chờ nhân sự",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__captain_rejected": "Đội trưởng từ chối",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__hr_reviewed": "Nhân sự đã đối chiếu",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__hr_discrepancy": "Nhân sự thấy lệch",
            "hr_attendance_portal.selection__hr_attendance__overtime_state__closed": "Đã chốt",
            "hr_attendance_portal.selection__hr_attendance__work_status__at_work": "Đang làm việc",
            "hr_attendance_portal.selection__hr_attendance__work_status__finished": "Đã kết thúc",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__pending_hr": "Chờ nhân sự",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__pending_captain": "Chờ đội trưởng",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__hr_reviewed": "Nhân sự đã đối chiếu",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__hr_discrepancy": "Nhân sự thấy lệch",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__captain_rejected": "Đội trưởng từ chối",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__corrected": "Đã điều chỉnh",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__correction_rejected": "Từ chối điều chỉnh",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__denied": "Từ chối",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__closed": "Đã chốt",
            "hr_attendance_portal.selection__hr_attendance__approved_list_status__done": "Hợp lệ",
        }
        for xmlid, label in field_labels.items():
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                record.with_context(lang="vi_VN").write({"field_description": label})
        for xmlid, label in selection_labels.items():
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                record.with_context(lang="vi_VN").write({"name": label})
        self._sync_edge_case_vietnamese_labels()
        self.env["hr.attendance"]._release_reviewed_overtime_sessions()

    @api.model
    def _sync_edge_case_vietnamese_labels(self):
        """Vietnamese labels for the captain session, overtime, and correction dialogs."""
        field_labels = {
            ("hr.attendance.hour.wizard", "decision_type"): "Loại quyết định",
            ("hr.attendance.hour.wizard", "hours"): "Giờ được công nhận",
            ("hr.attendance.hour.wizard", "reason"): "Lý do",
            ("hr.attendance.overtime.bulk.wizard", "shift_count"): "Số ca",
            ("hr.attendance.overtime.bulk.wizard", "reason"): "Lý do",
            ("hr.attendance.reduce.bulk.wizard", "shift_count"): "Số ca",
            ("hr.attendance.reduce.bulk.wizard", "hours"): "Giờ được công nhận",
            ("hr.attendance.reduce.bulk.wizard", "reason"): "Lý do",
            ("hr.attendance.checkout.wizard", "check_out"): "Giờ ra",
            ("hr.attendance.correction.bulk.wizard", "correction_type"): "Mốc giờ",
            ("hr.attendance.correction.bulk.wizard", "reason"): "Lý do",
            ("hr.attendance.correction.bulk.line", "employee_id"): "Nhân viên",
            ("hr.attendance.correction.bulk.line", "check_in"): "Giờ vào",
            ("hr.attendance.correction.bulk.line", "check_out"): "Giờ ra",
            ("hr.attendance.correction.bulk.line", "proposed_value"): "Giờ đề xuất",
            ("hr.attendance.checkout.wizard", "reason"): "Lý do",
            ("hr.attendance.hour.decision", "attendance_id"): "Ca",
            ("hr.attendance.hour.decision", "decision_type"): "Quyết định",
            ("hr.attendance.hour.decision", "regular_before"): "Giờ trước",
            ("hr.attendance.hour.decision", "regular_after"): "Giờ sau",
            ("hr.attendance.hour.decision", "reason"): "Lý do",
            ("hr.attendance.hour.decision", "user_id"): "Người quyết định",
            ("hr.attendance.hour.decision", "decided_at"): "Thời điểm",
            ("hr.attendance.hour.decision", "role"): "Vai trò",
            ("hr.attendance.overtime.wizard", "rejected"): "Từ chối làm thêm",
            ("hr.attendance.overtime.wizard", "hours"): "Giờ làm thêm duyệt",
            ("hr.attendance.overtime.wizard", "reason"): "Lý do",
            ("hr.attendance.overtime.hr.wizard", "discrepancy"): "Lệch số liệu",
            ("hr.attendance.overtime.hr.wizard", "hours"): "Giờ làm thêm tính lương",
            ("hr.attendance.overtime.hr.wizard", "note"): "Ghi chú đối chiếu",
            ("hr.attendance.overtime.case", "attendance_id"): "Ca",
            ("hr.attendance.overtime.case", "candidate_hours"): "Giờ làm thêm đề xuất",
            ("hr.attendance.overtime.case", "captain_hours"): "Giờ đội trưởng duyệt",
            ("hr.attendance.overtime.case", "hr_hours"): "Giờ nhân sự duyệt",
            ("hr.attendance.overtime.case", "payroll_hours"): "Giờ làm thêm tính lương",
            ("hr.attendance.overtime.case", "state"): "Trạng thái",
            ("hr.attendance.overtime.case", "captain_user_id"): "Đội trưởng",
            ("hr.attendance.overtime.case", "captain_at"): "Đội trưởng duyệt lúc",
            ("hr.attendance.overtime.case", "captain_reason"): "Lý do đội trưởng",
            ("hr.attendance.overtime.case", "hr_user_id"): "Nhân sự",
            ("hr.attendance.overtime.case", "hr_at"): "Nhân sự đối chiếu lúc",
            ("hr.attendance.overtime.case", "hr_note"): "Ghi chú nhân sự",
            ("hr.attendance.overtime.case", "decision_ids"): "Các quyết định",
            ("hr.attendance.overtime.decision", "decision_type"): "Quyết định",
            ("hr.attendance.overtime.decision", "hours_before"): "Giờ trước",
            ("hr.attendance.overtime.decision", "hours_after"): "Giờ sau",
            ("hr.attendance.overtime.decision", "reason"): "Lý do",
            ("hr.attendance.overtime.decision", "user_id"): "Người quyết định",
            ("hr.attendance.overtime.decision", "decided_at"): "Thời điểm",
            ("hr.attendance.correction.wizard", "correction_type"): "Mốc giờ",
            ("hr.attendance.correction.wizard", "proposed_value"): "Giờ đề xuất",
            ("hr.attendance.correction.wizard", "reason"): "Lý do",
            ("hr.attendance.correction", "attendance_id"): "Ca",
            ("hr.attendance.correction", "correction_type"): "Mốc giờ",
            ("hr.attendance.correction", "original_value"): "Giờ gốc",
            ("hr.attendance.correction", "proposed_value"): "Giờ đề xuất",
            ("hr.attendance.correction", "applied_value"): "Giờ đã áp dụng",
            ("hr.attendance.correction", "reason"): "Lý do",
            ("hr.attendance.correction", "requester_id"): "Người yêu cầu",
            ("hr.attendance.correction", "requested_at"): "Thời điểm yêu cầu",
            ("hr.attendance.correction", "state"): "Trạng thái",
            ("hr.attendance.correction", "decider_id"): "Người quyết định",
            ("hr.attendance.correction", "decided_at"): "Thời điểm",
            ("hr.attendance.correction", "decision_reason"): "Lý do quyết định",
            ("hr.attendance.timesheet.wizard", "department_id"): "Bãi xe",
            ("hr.attendance.timesheet.wizard", "date_from"): "Từ ngày",
            ("hr.attendance.timesheet.wizard", "date_to"): "Đến ngày",
        }
        selection_labels = {
            ("hr.attendance.hour.wizard", "decision_type"): {
                "deny_session": "Từ chối ca",
                "reduce_regular": "Giảm giờ",
                "restore_session": "Khôi phục ca",
            },
            ("hr.attendance.hour.decision", "decision_type"): {
                "deny_session": "Từ chối ca",
                "reduce_regular": "Giảm giờ",
                "restore_session": "Khôi phục ca",
                "confirm_checkout": "Xác nhận giờ ra",
            },
            ("hr.attendance.hour.decision", "role"): {
                "captain": "Đội trưởng",
                "hr": "Nhân sự",
            },
            ("hr.attendance.correction.wizard", "correction_type"): {
                "check_in": "Giờ vào",
                "check_out": "Giờ ra",
            },
            ("hr.attendance.correction.bulk.wizard", "correction_type"): {
                "check_in": "Giờ vào",
                "check_out": "Giờ ra",
            },
            ("hr.attendance.correction", "correction_type"): {
                "check_in": "Giờ vào",
                "check_out": "Giờ ra",
            },
            ("hr.attendance.correction", "state"): {
                "pending": "Chờ duyệt",
                "approved": "Đã duyệt",
                "rejected": "Từ chối",
            },
            ("hr.attendance.overtime.case", "state"): {
                "not_required": "Không có",
                "pending_captain": "Chờ đội trưởng",
                "pending_hr_review": "Chờ nhân sự",
                "captain_rejected": "Đội trưởng từ chối",
                "hr_reviewed": "Nhân sự đã đối chiếu",
                "hr_discrepancy": "Nhân sự thấy lệch",
                "closed": "Đã chốt",
            },
            ("hr.attendance.overtime.decision", "decision_type"): {
                "captain_approve": "Đội trưởng duyệt",
                "captain_reject": "Đội trưởng từ chối",
                "hr_review": "Nhân sự đối chiếu",
                "hr_discrepancy": "Nhân sự thấy lệch",
            },
        }
        Fields = self.env["ir.model.fields"].sudo()
        Selection = self.env["ir.model.fields.selection"].sudo()
        for (model, name), label in field_labels.items():
            field = Fields._get(model, name)
            if field:
                field.with_context(lang="vi_VN").write({"field_description": label})
        for (model, name), values in selection_labels.items():
            field = Fields._get(model, name)
            if not field:
                continue
            for value, label in values.items():
                selection = Selection.search([
                    ("field_id", "=", field.id),
                    ("value", "=", value),
                ], limit=1)
                if selection:
                    selection.with_context(lang="vi_VN").write({"name": label})

        terms = {
            "Deny Session": "Từ chối ca",
            "Deny this shift?": "Từ chối ca này?",
            "Reduce Hours": "Giảm giờ",
            "Reduce Selected Hours": "Giảm giờ đã chọn",
            "Review Overtime": "Duyệt làm thêm",
            "Approve Selected Overtime": "Duyệt làm thêm đã chọn",
            "Reject Selected Overtime": "Từ chối làm thêm đã chọn",
            "Request Time Correction": "Xin điều chỉnh giờ",
            "HR Overtime Review": "Nhân sự đối chiếu làm thêm",
            "Restore Session": "Khôi phục ca",
            "Close Session": "Chốt ca",
            "Reopen Session": "Bỏ chốt",
            "Reopen this shift?": "Bỏ chốt ca này?",
            "Hour Decisions": "Quyết định giờ",
            "Time Corrections": "Điều chỉnh giờ",
            "Confirm": "Xác nhận",
            "Confirm Checkout": "Xác nhận giờ ra",
            "Checkout Time": "Giờ ra",
            "Cancel": "Hủy",
            "Send to HR": "Gửi nhân sự",
            "Approve": "Duyệt",
            "Reject": "Từ chối",
            "Overtime Hours": "Giờ làm thêm",
            "Overtime To Review": "Làm thêm cần duyệt",
            "Overtime From 1 Hour": "Vượt chuẩn từ 1 giờ",
            "Overtime Under 1 Hour": "Tăng ca dưới 1 giờ",
            "Pending Review": "Cần xử lý",
            "Missing Checkout": "Quên giờ ra",
            "Session Status": "Trạng thái ca",
            "Exception": "Ngoại lệ",
            "Check-in Photo": "Ảnh lúc vào",
            "Check-out Photo": "Ảnh lúc ra",
            "Events": "Lượt chấm",
            "Time In": "Giờ vào",
            "Time Out": "Giờ ra",
            "Status": "Trạng thái",
            "Reason": "Lý do",
            "Captain Hours": "Giờ đội trưởng duyệt",
            "Captain Reason": "Lý do đội trưởng",
            "Review Note": "Ghi chú nhân sự",
            "Shifts": "Số ca",
            "Export Timesheet": "Xuất bảng công",
        }
        for xmlid in (
            "hr_attendance_portal.view_hr_attendance_form_portal",
            "hr_attendance_portal.view_hr_attendance_hour_wizard_form",
            "hr_attendance_portal.view_hr_attendance_overtime_wizard_form",
            "hr_attendance_portal.view_hr_attendance_overtime_bulk_wizard_form",
            "hr_attendance_portal.view_hr_attendance_overtime_hr_wizard_form",
            "hr_attendance_portal.view_hr_attendance_checkout_wizard_form",
            "hr_attendance_portal.view_hr_attendance_correction_wizard_form",
            "hr_attendance_portal.view_hr_attendance_reduce_bulk_wizard_form",
            "hr_attendance_portal.view_hr_attendance_correction_bulk_wizard_form",
            "hr_attendance_portal.view_hr_attendance_correction_form",
            "hr_attendance_portal.view_attendance_search_captain",
            "hr_attendance_portal.view_attendance_tree_portal",
            "hr_attendance_portal.view_attendance_tree_captain",
            "hr_attendance_portal.view_attendance_tree_captain_session",
            "hr_attendance_portal.view_attendance_tree_hr_overtime",
            "hr_attendance_portal.view_attendance_tree_overtime_approved",
            "hr_attendance_portal.view_hr_attendance_overtime_hr_bulk_wizard_form",
            "hr_attendance_portal.view_hr_attendance_form_captain",
            "hr_attendance_portal.view_hr_attendance_timesheet_wizard_form",
        ):
            view = self.env.ref(xmlid, raise_if_not_found=False)
            if view:
                view.sudo().update_field_translations("arch_db", {"vi_VN": terms})
        self._sync_valid_attendance_label()
