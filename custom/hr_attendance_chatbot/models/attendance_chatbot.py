# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

import requests
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.osv import expression
from odoo.tools import float_compare, float_round

_logger = logging.getLogger(__name__)

ICP_BASE = "hr_attendance_chatbot.litellm_base_url"
ICP_MODEL = "hr_attendance_chatbot.litellm_model"
ICP_KEY = "hr_attendance_chatbot.litellm_api_key"
PROPOSAL_TTL_MINUTES = 30
MAX_LLM_ROUNDS = 8
HISTORY_LIMIT = 40


class HrAttendanceChatbot(models.AbstractModel):
    _name = "hr.attendance.chatbot"
    _description = "Attendance chatbot (LiteLLM, server-side tools)"

    def _icp(self):
        return self.env["ir.config_parameter"].sudo()

    @api.model
    def user_is_eligible(self, user=None):
        user = user or self.env.user
        return (
            user.has_group("hr_attendance.group_hr_attendance_officer")
            or user.has_group("hr_attendance_portal.group_hr_attendance_site_captain")
        )

    @api.model
    def bot_is_configured(self):
        model = (self._icp().get_param(ICP_MODEL) or "").strip()
        base = (self._icp().get_param(ICP_BASE) or "").strip()
        return bool(model and base)

    @api.model
    def session_status(self):
        eligible = self.user_is_eligible()
        configured = self.bot_is_configured()
        reason = ""
        if not eligible:
            reason = "Chỉ đội trưởng công trường và nhân sự chấm công được dùng trợ lý."
        elif not configured:
            reason = "Trợ lý chưa được cấu hình trên máy chủ (thiếu URL hoặc tên model LiteLLM)."
        return {
            "eligible": eligible,
            "enabled": eligible and configured,
            "offline_reason": reason,
        }

    @api.model
    def _check_chat_access(self):
        if not self.user_is_eligible():
            raise AccessError(self.env._("You cannot use the attendance assistant."))
        if not self.bot_is_configured():
            raise UserError(self.env._(
                "The attendance assistant is not configured on the server."
            ))

    def _litellm_config(self):
        icp = self._icp()
        base = (icp.get_param(ICP_BASE) or "").strip().rstrip("/")
        model = (icp.get_param(ICP_MODEL) or "").strip()
        api_key = (icp.get_param(ICP_KEY) or "").strip()
        if not base or not model:
            raise UserError(self.env._(
                "LiteLLM base URL and model must be set in system parameters."
            ))
        return base, model, api_key

    def _system_prompt(self):
        return (
            "Bạn là trợ lý chấm công cho đội trưởng công trường và nhân sự HR tại Kien Viet. "
            "Trả lời bằng tiếng Việt, ngắn gọn và chính xác. "
            "Bạn chỉ được dùng công cụ (tools) để đọc ca chấm công mà người dùng đã được phép xem "
            "hoặc để ĐỀ XUẤT thay đổi; bạn không tự ghi dữ liệu. "
            "Mọi ghi (điều chỉnh giờ công nhận hoặc duyệt tăng ca) cần lý do bằng lời người dùng — "
            "nếu thiếu lý do, hãy hỏi trước khi gọi công cụ đề xuất. "
            "Khi đề xuất tổng giờ công nhận vượt giờ chuẩn ngày, giờ chuẩn giữ nguyên và phần dư "
            "trở thành tăng ca đã duyệt (theo logic sẵn có của hệ thống). "
            "Không đề xuất các thao tác khác ngoài điều chỉnh giờ công nhận và duyệt/từ chối tăng ca đội trưởng."
        )

    def _tool_definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_attendances",
                    "description": (
                        "Tìm ca chấm công người dùng được phép xem: theo tên/mã NV và ngày, "
                        "hoặc danh sách chờ duyệt."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_query": {
                                "type": "string",
                                "description": "Tên hoặc mã nhân viên (emp_code), tùy chọn.",
                            },
                            "work_date": {
                                "type": "string",
                                "description": "Ngày làm việc ISO (YYYY-MM-DD), tùy chọn.",
                            },
                            "review_queue": {
                                "type": "boolean",
                                "description": "True để lấy ca đang chờ duyệt / ngoại lệ.",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Số dòng tối đa (mặc định 15, tối đa 25).",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_attendance_detail",
                    "description": "Chi tiết một ca theo attendance_id.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "attendance_id": {"type": "integer"},
                        },
                        "required": ["attendance_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "propose_reduce_regular",
                    "description": (
                        "Đề xuất đặt tổng giờ công nhận cho ca (action_reduce_regular). "
                        "Cần attendance_id, hours, reason."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "attendance_id": {"type": "integer"},
                            "hours": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["attendance_id", "hours", "reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "propose_captain_overtime",
                    "description": (
                        "Đề xuất duyệt hoặc từ chối tăng ca đang chờ (action_captain_overtime)."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "attendance_id": {"type": "integer"},
                            "hours": {"type": "number"},
                            "reason": {"type": "string"},
                            "rejected": {"type": "boolean"},
                        },
                        "required": ["attendance_id", "hours", "reason", "rejected"],
                    },
                },
            },
        ]

    @api.model
    def _format_dt(self, dt):
        if not dt:
            return ""
        return fields.Datetime.context_timestamp(self, dt).strftime("%d/%m/%Y %H:%M")

    @api.model
    def _format_date(self, d):
        if not d:
            return ""
        return fields.Date.to_string(d)

    def _attendance_work_date(self, attendance):
        start = attendance.effective_check_in or attendance.check_in
        if not start:
            return False
        return fields.Datetime.context_timestamp(self, start).date()

    def _serialize_attendance(self, attendance, detailed=False):
        employee = attendance.employee_id
        location = attendance.in_location_id or attendance.out_location_id
        data = {
            "attendance_id": attendance.id,
            "employee_name": employee.name,
            "emp_code": getattr(employee, "emp_code", False) or "",
            "work_date": self._format_date(self._attendance_work_date(attendance)),
            "workplace": location.display_name if location else "",
            "check_in": self._format_dt(attendance.check_in),
            "check_out": self._format_dt(attendance.check_out),
            "effective_check_in": self._format_dt(attendance.effective_check_in),
            "effective_check_out": self._format_dt(attendance.effective_check_out),
            "session_state": attendance.session_state,
            "overtime_state": attendance.overtime_state,
            "recognized_regular_hours": attendance.recognized_regular_hours,
            "payroll_regular_hours": attendance.payroll_regular_hours,
            "payroll_overtime_hours": attendance.payroll_overtime_hours,
            "overtime_candidate_hours": attendance.overtime_candidate_hours,
            "standard_hours": attendance.standard_hours,
        }
        if detailed:
            case = attendance.overtime_case_ids[:1]
            data["overtime_case_state"] = case.state if case else False
            data["reason_required_for_write"] = attendance.session_state == "closed"
            if attendance.session_state == "closed":
                data["write_blocked"] = self.env._("Session is closed.")
            elif attendance.session_state == "denied":
                data["write_blocked"] = self.env._("Session is denied.")
            elif not attendance.check_out and not attendance.effective_check_out:
                data["write_blocked"] = self.env._("Checkout not confirmed yet.")
        return data

    @api.model
    def _search_attendances_tool(
        self, employee_query=None, work_date=None, review_queue=False, limit=15
    ):
        limit = max(1, min(int(limit or 15), 25))
        Attendance = self.env["hr.attendance"]
        parts = []
        if review_queue:
            parts.append([
                "|",
                ("session_state", "=", "pending_review"),
                ("exception_code", "=", "missing_checkout"),
            ])
        if work_date:
            day = fields.Date.from_string(work_date)
            start = fields.Datetime.to_datetime(day)
            end = start + timedelta(days=1)
            parts.append([
                "|",
                "&",
                ("check_in", ">=", start),
                ("check_in", "<", end),
                "&",
                ("effective_check_in", ">=", start),
                ("effective_check_in", "<", end),
            ])
        if employee_query:
            query = (employee_query or "").strip()
            parts.append([
                "|",
                ("employee_id.name", "ilike", query),
                ("employee_id.emp_code", "ilike", query),
            ])
        domain = expression.AND(parts) if parts else []
        records = Attendance.search(domain, limit=limit, order="check_in desc, id desc")
        return {"count": len(records), "attendances": [
            self._serialize_attendance(rec) for rec in records
        ]}

    def _get_attendance_detail_tool(self, attendance_id):
        attendance = self.env["hr.attendance"].browse(int(attendance_id))
        if not attendance.exists():
            return {"error": self.env._("Attendance not found.")}
        attendance._check_session_visible()
        return {"attendance": self._serialize_attendance(attendance, detailed=True)}

    def _preview_reduce_regular(self, attendance, hours):
        company = attendance.employee_id.company_id or self.env.company
        standard = attendance.standard_hours or company.attendance_standard_hours or 8.0
        before = {
            "recognized_regular_hours": attendance.recognized_regular_hours,
            "payroll_regular_hours": attendance.payroll_regular_hours,
            "payroll_overtime_hours": attendance.payroll_overtime_hours,
            "overtime_state": attendance.overtime_state,
        }
        if float_compare(hours, standard, precision_digits=4) <= 0:
            after = {
                "recognized_regular_hours": hours,
                "payroll_regular_hours": hours,
                "payroll_overtime_hours": 0.0,
                "overtime_state": "not_required",
                "note": self.env._("All recognized time counts as regular hours."),
            }
        else:
            ot = hours - standard
            after = {
                "recognized_regular_hours": standard,
                "payroll_regular_hours": standard,
                "payroll_overtime_hours": ot,
                "overtime_state": "captain_reviewed",
                "note": self.env._(
                    "Regular hours stay at the standard day; excess becomes captain-approved overtime."
                ),
            }
        return before, after

    def _build_reduce_summary(self, attendance, hours, reason, before, after):
        employee = attendance.employee_id.name
        work_date = self._format_date(self._attendance_work_date(attendance))
        return self.env._(
            "Đề xuất điều chỉnh giờ công nhận — %(employee)s, ca %(date)s:\n"
            "Trước: %(bh)sgiờ công nhận, %(bp)sgiờ lương chính, %(bo)sgiờ tăng ca.\n"
            "Sau (khi xác nhận): %(ah)sgiờ công nhận, %(ap)sgiờ lương chính, %(ao)sgiờ tăng ca "
            "(%(ostate)s).\n"
            "Lý do: %(reason)s",
            employee=employee,
            date=work_date,
            bh=float_round(before["recognized_regular_hours"], precision_digits=2),
            bp=float_round(before["payroll_regular_hours"], precision_digits=2),
            bo=float_round(before["payroll_overtime_hours"], precision_digits=2),
            ah=float_round(after["recognized_regular_hours"], precision_digits=2),
            ap=float_round(after["payroll_regular_hours"], precision_digits=2),
            ao=float_round(after["payroll_overtime_hours"], precision_digits=2),
            ostate=after["overtime_state"],
            reason=reason,
        )

    def _validate_reduce_proposal(self, attendance, hours, reason):
        attendance._check_session_visible()
        attendance._ensure_session_open()
        if attendance.session_state == "denied":
            raise UserError(self.env._("A denied session has no hours to reduce."))
        attendance._session_actor_role()
        attendance._require_reason(reason)
        _start, end = attendance._session_bounds()
        if not end:
            raise UserError(self.env._("Confirm checkout before reducing hours."))
        duration = attendance._session_duration()
        if float_compare(hours, 0.0, precision_digits=4) < 0:
            raise UserError(self.env._("Recognized hours cannot be negative."))
        if float_compare(hours, duration, precision_digits=4) > 0:
            raise UserError(self.env._(
                "Recognized hours cannot exceed the elapsed time."
            ))

    def _validate_overtime_proposal(self, attendance, hours, reason, rejected):
        attendance._check_session_visible()
        attendance._ensure_session_open()
        if attendance.session_state == "denied":
            raise UserError(self.env._("A denied session has no overtime to review."))
        attendance._session_actor_role()
        attendance._require_reason(reason)
        case = attendance.overtime_case_ids[:1]
        if not case:
            raise UserError(self.env._("This session has no overtime to review."))
        if rejected:
            return
        if float_compare(hours, 0.0, precision_digits=4) < 0:
            raise UserError(self.env._("Overtime hours cannot be negative."))

    def _create_proposal(self, attendance, method, arguments, reason, summary):
        Proposal = self.env["hr.attendance.chat.proposal"]
        expires = fields.Datetime.now() + timedelta(minutes=PROPOSAL_TTL_MINUTES)
        proposal = Proposal.create({
            "attendance_id": attendance.id,
            "method": method,
            "argument_json": json.dumps(arguments),
            "reason": reason,
            "summary_vi": summary,
            "expires_at": expires,
        })
        return proposal

    def _propose_reduce_regular_tool(self, attendance_id, hours, reason):
        attendance = self.env["hr.attendance"].browse(int(attendance_id))
        if not attendance.exists():
            return {"error": self.env._("Attendance not found.")}
        reason = (reason or "").strip()
        if not reason:
            return {"error": self.env._("A reason is required before proposing a change.")}
        try:
            self._validate_reduce_proposal(attendance, float(hours), reason)
        except (UserError, AccessError) as exc:
            return {"error": str(exc)}
        before, after = self._preview_reduce_regular(attendance, float(hours))
        summary = self._build_reduce_summary(attendance, float(hours), reason, before, after)
        proposal = self._create_proposal(
            attendance,
            "action_reduce_regular",
            {"hours": float(hours), "reason": reason},
            reason,
            summary,
        )
        return {
            "proposal_id": proposal.id,
            "summary_vi": summary,
            "awaiting_user_confirm": True,
        }

    def _propose_captain_overtime_tool(self, attendance_id, hours, reason, rejected=False):
        attendance = self.env["hr.attendance"].browse(int(attendance_id))
        if not attendance.exists():
            return {"error": self.env._("Attendance not found.")}
        reason = (reason or "").strip()
        rejected = bool(rejected)
        if not reason:
            return {"error": self.env._("A reason is required before proposing a change.")}
        try:
            self._validate_overtime_proposal(attendance, float(hours), reason, rejected)
        except (UserError, AccessError) as exc:
            return {"error": str(exc)}
        employee = attendance.employee_id.name
        work_date = self._format_date(self._attendance_work_date(attendance))
        case = attendance.overtime_case_ids[:1]
        if rejected:
            summary = self.env._(
                "Đề xuất từ chối tăng ca — %(employee)s, ca %(date)s. "
                "Ứng viên tăng ca: %(cand)sgiờ. Lý do: %(reason)s",
                employee=employee,
                date=work_date,
                cand=case.candidate_hours if case else 0,
                reason=reason,
            )
        else:
            summary = self.env._(
                "Đề xuất duyệt tăng ca — %(employee)s, ca %(date)s: "
                "%(hours)sgiờ (ứng viên %(cand)sgiờ). Lý do: %(reason)s",
                employee=employee,
                date=work_date,
                hours=float(hours),
                cand=case.candidate_hours if case else 0,
                reason=reason,
            )
        proposal = self._create_proposal(
            attendance,
            "action_captain_overtime",
            {"hours": float(hours), "reason": reason, "rejected": rejected},
            reason,
            summary,
        )
        return {
            "proposal_id": proposal.id,
            "summary_vi": summary,
            "awaiting_user_confirm": True,
        }

    def _run_tool(self, name, arguments):
        args = arguments or {}
        if name == "search_attendances":
            return self._search_attendances_tool(**args)
        if name == "get_attendance_detail":
            return self._get_attendance_detail_tool(args.get("attendance_id"))
        if name == "propose_reduce_regular":
            return self._propose_reduce_regular_tool(
                args.get("attendance_id"),
                args.get("hours"),
                args.get("reason"),
            )
        if name == "propose_captain_overtime":
            return self._propose_captain_overtime_tool(
                args.get("attendance_id"),
                args.get("hours"),
                args.get("reason"),
                args.get("rejected", False),
            )
        return {"error": self.env._("Unknown tool.")}

    def _load_llm_messages(self):
        Message = self.env["hr.attendance.chat.message"]
        lines = Message.search([("user_id", "=", self.env.uid)], limit=HISTORY_LIMIT, order="id desc")
        history = []
        for line in reversed(lines):
            history.append({
                "role": "assistant" if line.role == "assistant" else "user",
                "content": line.body,
            })
        return history

    def _call_litellm(self, messages):
        base, model, api_key = self._litellm_config()
        url = f"{base}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": self._system_prompt()}] + messages,
            "tools": self._tool_definitions(),
            "tool_choice": "auto",
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            _logger.warning("LiteLLM request failed: %s", exc)
            raise UserError(self.env._(
                "Cannot reach LiteLLM on the server. Check URL, model, and API key."
            )) from exc

    def _message_proposals_from_round(self, tool_results):
        """Collect proposal ids created in this assistant turn."""
        ids = []
        for result in tool_results:
            if isinstance(result, dict) and result.get("proposal_id"):
                ids.append(result["proposal_id"])
        return ids

    @api.model
    def chat_send(self, text):
        self._check_chat_access()
        text = (text or "").strip()
        if not text:
            raise UserError(self.env._("Message cannot be empty."))
        Message = self.env["hr.attendance.chat.message"]
        Message.create({"role": "user", "body": text})
        messages = self._load_llm_messages()
        created_proposals = []
        assistant_text = ""
        for _round in range(MAX_LLM_ROUNDS):
            data = self._call_litellm(messages)
            choices = data.get("choices") or []
            if not choices:
                raise UserError(self.env._("LiteLLM returned an empty response."))
            message = choices[0].get("message") or {}
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                messages.append(message)
                round_proposals = []
                for call in tool_calls:
                    fn = (call.get("function") or {})
                    name = fn.get("name")
                    try:
                        arguments = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    result = self._run_tool(name, arguments)
                    created_proposals.extend(
                        [result["proposal_id"]] if result.get("proposal_id") else []
                    )
                    round_proposals.append(result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                if round_proposals and not message.get("content"):
                    continue
            assistant_text = (message.get("content") or "").strip()
            if not assistant_text and created_proposals:
                summaries = self.env["hr.attendance.chat.proposal"].browse(
                    created_proposals
                ).mapped("summary_vi")
                assistant_text = "\n\n".join(summaries)
            break
        else:
            raise UserError(self.env._("The assistant took too many steps. Try a simpler question."))

        if not assistant_text:
            assistant_text = self.env._("Done. Please review the proposal and confirm in the chat.")

        msg = Message.create({"role": "assistant", "body": assistant_text})
        if created_proposals:
            for pid in created_proposals:
                proposal = self.env["hr.attendance.chat.proposal"].browse(pid)
                if proposal.exists():
                    msg.proposal_id = proposal.id
                    break
        return self.chat_history()

    @api.model
    def chat_history(self):
        self._check_chat_access()
        self._expire_old_proposals()
        Message = self.env["hr.attendance.chat.message"]
        Proposal = self.env["hr.attendance.chat.proposal"]
        messages = Message.search([("user_id", "=", self.env.uid)], limit=HISTORY_LIMIT)
        pending = Proposal.search([
            ("user_id", "=", self.env.uid),
            ("state", "=", "pending"),
        ])
        proposal_by_id = {p.id: p for p in pending}
        items = []
        for line in messages:
            item = {
                "id": line.id,
                "role": line.role,
                "body": line.body,
                "proposal": False,
            }
            pid = line.proposal_id.id
            if pid and pid in proposal_by_id:
                proposal = proposal_by_id[pid]
                item["proposal"] = {
                    "id": proposal.id,
                    "summary_vi": proposal.summary_vi,
                    "method": proposal.method,
                    "state": proposal.state,
                    "expires_at": fields.Datetime.to_string(proposal.expires_at),
                }
            items.append(item)
        return {"messages": items, "pending_proposals": [
            {
                "id": p.id,
                "summary_vi": p.summary_vi,
                "method": p.method,
                "state": p.state,
                "expires_at": fields.Datetime.to_string(p.expires_at),
            }
            for p in pending
        ]}

    @api.model
    def _expire_old_proposals(self):
        now = fields.Datetime.now()
        stale = self.env["hr.attendance.chat.proposal"].search([
            ("user_id", "=", self.env.uid),
            ("state", "=", "pending"),
            ("expires_at", "<", now),
        ])
        if stale:
            stale.write({"state": "expired"})

    @api.model
    def confirm_proposal(self, proposal_id):
        self._check_chat_access()
        self._expire_old_proposals()
        proposal = self.env["hr.attendance.chat.proposal"].browse(int(proposal_id))
        if not proposal.exists() or proposal.user_id.id != self.env.uid:
            raise AccessError(self.env._("Proposal not found."))
        if proposal.state != "pending":
            raise UserError(self.env._("This proposal is no longer pending."))
        if proposal.expires_at < fields.Datetime.now():
            proposal.write({"state": "expired"})
            raise UserError(self.env._("This proposal has expired."))
        attendance = proposal.attendance_id
        attendance._check_session_visible()
        args = proposal.get_arguments()
        try:
            if proposal.method == "action_reduce_regular":
                attendance.action_reduce_regular(args["hours"], args["reason"])
            elif proposal.method == "action_captain_overtime":
                attendance.action_captain_overtime(
                    args["hours"],
                    args["reason"],
                    rejected=args.get("rejected", False),
                )
            else:
                raise UserError(self.env._("Unsupported action."))
        except (UserError, AccessError) as exc:
            proposal.write({"error_message": str(exc)})
            Message = self.env["hr.attendance.chat.message"]
            Message.create({
                "role": "assistant",
                "body": str(exc),
                "proposal_id": proposal.id,
            })
            return self.chat_history()
        proposal.write({
            "state": "confirmed",
            "confirmed_at": fields.Datetime.now(),
        })
        Message = self.env["hr.attendance.chat.message"]
        Message.create({
            "role": "assistant",
            "body": self.env._("Đã xác nhận và ghi ca chấm công thành công."),
            "proposal_id": proposal.id,
        })
        return self.chat_history()

    @api.model
    def dismiss_proposal(self, proposal_id):
        self._check_chat_access()
        proposal = self.env["hr.attendance.chat.proposal"].browse(int(proposal_id))
        if not proposal.exists() or proposal.user_id.id != self.env.uid:
            raise AccessError(self.env._("Proposal not found."))
        if proposal.state == "pending":
            proposal.write({"state": "dismissed"})
        return self.chat_history()