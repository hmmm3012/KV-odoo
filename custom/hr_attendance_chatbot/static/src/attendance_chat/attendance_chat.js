/** @odoo-module **/

import { Component, onMounted, useEffect, useRef, useState } from "@odoo/owl";
import { markdownToSafeMarkup } from "./markdown_safe";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { session } from "@web/session";
import { useService } from "@web/core/utils/hooks";

let localMsgSeq = 0;

export class AttendanceChat extends Component {
    static template = "hr_attendance_chatbot.AttendanceChat";
    static props = {};

    setup() {
        const chatInfo = session.attendance_chatbot || {};
        this.notification = useService("notification");
        this.messagesRef = useRef("messages");
        this.textareaRef = useRef("textarea");
        this.state = useState({
            open: false,
            enabled: Boolean(chatInfo.enabled),
            offlineReason: chatInfo.offline_reason || _t("Trợ lý không khả dụng."),
            messages: [],
            pendingProposals: [],
            draft: "",
            loadingHistory: false,
            sending: false,
        });
        onMounted(() => {
            if (this.state.enabled && this.state.open) {
                void this.refreshHistory();
            }
        });
        useEffect(
            () => {
                this._scrollToBottom();
            },
            () => [this.state.messages.length, this.state.open]
        );
    }

    get canSend() {
        return Boolean((this.state.draft || "").trim()) && !this.state.sending;
    }

    get userName() {
        return session.name || _t("Bạn");
    }

    messageMarkup(msg) {
        if (msg.status === "typing") {
            return null;
        }
        if (msg.role === "assistant" || msg.role === "user") {
            return markdownToSafeMarkup(msg.body || "");
        }
        return markdownToSafeMarkup(msg.body || "");
    }

    formatTime(iso) {
        if (!iso) {
            return "";
        }
        try {
            const normalized = iso.includes("T") ? iso : `${iso.replace(" ", "T")}Z`;
            const d = new Date(normalized);
            return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        } catch {
            return "";
        }
    }

    _scrollToBottom() {
        const el = this.messagesRef.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }

    applyHistoryData(data) {
        const messages = data.messages || [];
        const linked = new Set(
            messages.filter((m) => m.proposal).map((m) => m.proposal.id)
        );
        this.state.messages = messages.map((m) => ({
            ...m,
            status: "sent",
            markup: null,
        }));
        this.state.pendingProposals = (data.pending_proposals || []).filter(
            (p) => p.state === "pending" && !linked.has(p.id)
        );
    }

    async refreshHistory() {
        this.state.loadingHistory = true;
        try {
            const data = await rpc("/attendance_chatbot/history");
            this.applyHistoryData(data);
        } catch (error) {
            this.notification.add(error?.message || _t("Không tải được hội thoại."), {
                type: "danger",
            });
        } finally {
            this.state.loadingHistory = false;
        }
    }

    toggle() {
        this.state.open = !this.state.open;
        if (this.state.open && this.state.enabled) {
            void this.refreshHistory();
        }
    }

    _appendLocalMessage(partial) {
        const id = `local-${++localMsgSeq}`;
        const row = {
            id,
            role: partial.role,
            body: partial.body || "",
            status: partial.status || "sent",
            error: partial.error || false,
            created_at: partial.created_at,
            proposal: partial.proposal || false,
        };
        this.state.messages.push(row);
        return row;
    }

    async _consumeStream(userMessageId, assistantRow) {
        const url = `/attendance_chatbot/message_stream?user_message_id=${encodeURIComponent(
            userMessageId
        )}`;
        const response = await fetch(url, {
            method: "GET",
            credentials: "include",
        });
        if (!response.ok) {
            throw new Error(_t("Luồng trợ lý thất bại."));
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        assistantRow.status = "streaming";
        assistantRow.body = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split("\n\n");
            buffer = parts.pop() || "";
            for (const part of parts) {
                const line = part.split("\n").find((l) => l.startsWith("data: "));
                if (!line) {
                    continue;
                }
                const payload = JSON.parse(line.slice(6));
                if (payload.type === "token") {
                    assistantRow.body += payload.delta || "";
                    this._scrollToBottom();
                } else if (payload.type === "done") {
                    assistantRow.status = "sent";
                    this.applyHistoryData(payload.history);
                    return;
                } else if (payload.type === "error") {
                    throw new Error(payload.message || _t("Lỗi trợ lý."));
                }
            }
        }
        assistantRow.status = "sent";
        await this.refreshHistory();
    }

    async onSend() {
        const text = (this.state.draft || "").trim();
        if (!text || this.state.sending) {
            return;
        }
        this.state.sending = true;
        this.state.draft = "";
        const userRow = this._appendLocalMessage({
            role: "user",
            body: text,
            status: "sent",
            created_at: new Date().toISOString(),
        });
        const assistantRow = this._appendLocalMessage({
            role: "assistant",
            body: "",
            status: "typing",
        });
        this._scrollToBottom();

        try {
            const { user_message_id: userMessageId } = await rpc(
                "/attendance_chatbot/message_prepare",
                { text }
            );
            userRow.id = userMessageId;
            await this._consumeStream(userMessageId, assistantRow);
        } catch (error) {
            userRow.status = "error";
            userRow.error = true;
            assistantRow.status = "error";
            assistantRow.body =
                error?.message || _t("Không gửi được tin nhắn. Thử lại sau.");
            this.notification.add(assistantRow.body, { type: "danger" });
        } finally {
            this.state.sending = false;
            this._scrollToBottom();
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            if (this.canSend) {
                void this.onSend();
            }
        }
    }

    async onConfirm(proposalId) {
        if (this.state.sending) {
            return;
        }
        this.state.sending = true;
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
            this.state.sending = false;
        }
    }

    async onDismiss(proposalId) {
        if (this.state.sending) {
            return;
        }
        this.state.sending = true;
        try {
            const data = await rpc("/attendance_chatbot/dismiss", {
                proposal_id: proposalId,
            });
            this.applyHistoryData(data);
            this._scrollToBottom();
        } catch (error) {
            this.notification.add(error?.message || _t("Không hủy được đề xuất."), {
                type: "danger",
            });
        } finally {
            this.state.sending = false;
        }
    }
}