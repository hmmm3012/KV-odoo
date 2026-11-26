/** @odoo-module **/

import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { session } from "@web/session";
import { useService } from "@web/core/utils/hooks";

export class AttendanceChat extends Component {
    static template = "hr_attendance_chatbot.AttendanceChat";
    static props = {};

    setup() {
        const chatInfo = session.attendance_chatbot || {};
        this.notification = useService("notification");
        this.messagesRef = useRef("messages");
        this.state = useState({
            open: false,
            enabled: Boolean(chatInfo.enabled),
            offlineReason: chatInfo.offline_reason || _t("Trợ lý không khả dụng."),
            messages: [],
            pendingProposals: [],
            draft: "",
            loading: false,
            busy: false,
        });
        onMounted(() => {
            if (this.state.enabled) {
                void this.refreshHistory();
            }
        });
    }

    async refreshHistory() {
        this.state.loading = true;
        try {
            const data = await rpc("/attendance_chatbot/history");
            const messages = data.messages || [];
            const linked = new Set(
                messages.filter((m) => m.proposal).map((m) => m.proposal.id)
            );
            this.state.messages = messages;
            this.state.pendingProposals = (data.pending_proposals || []).filter(
                (p) => p.state === "pending" && !linked.has(p.id)
            );
            this._scrollToBottom();
        } catch (error) {
            this.notification.add(error?.message || _t("Không tải được hội thoại."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    _scrollToBottom() {
        const el = this.messagesRef.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }

    toggle() {
        this.state.open = !this.state.open;
        if (this.state.open && this.state.enabled) {
            void this.refreshHistory();
        }
    }

    async onSend() {
        const text = (this.state.draft || "").trim();
        if (!text || this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.draft = "";
        try {
            const data = await rpc("/attendance_chatbot/message", { text });
            const messages = data.messages || [];
            const linked = new Set(
                messages.filter((m) => m.proposal).map((m) => m.proposal.id)
            );
            this.state.messages = messages;
            this.state.pendingProposals = (data.pending_proposals || []).filter(
                (p) => p.state === "pending" && !linked.has(p.id)
            );
            this._scrollToBottom();
        } catch (error) {
            this.notification.add(error?.message || _t("Gửi tin nhắn thất bại."), {
                type: "danger",
            });
        } finally {
            this.state.busy = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            void this.onSend();
        }
    }

    async onConfirm(proposalId) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await rpc("/attendance_chatbot/confirm", { proposal_id: proposalId });
            await this.refreshHistory();
            this.notification.add(_t("Đã xác nhận thay đổi."), { type: "success" });
        } catch (error) {
            await this.refreshHistory();
            this.notification.add(error?.message || _t("Xác nhận thất bại."), {
                type: "danger",
            });
        } finally {
            this.state.busy = false;
        }
    }

    async onDismiss(proposalId) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const data = await rpc("/attendance_chatbot/dismiss", { proposal_id: proposalId });
            const messages = data.messages || [];
            const linked = new Set(
                messages.filter((m) => m.proposal).map((m) => m.proposal.id)
            );
            this.state.messages = messages;
            this.state.pendingProposals = (data.pending_proposals || []).filter(
                (p) => p.state === "pending" && !linked.has(p.id)
            );
            this._scrollToBottom();
        } catch (error) {
            this.notification.add(error?.message || _t("Không hủy được đề xuất."), {
                type: "danger",
            });
        } finally {
            this.state.busy = false;
        }
    }
}