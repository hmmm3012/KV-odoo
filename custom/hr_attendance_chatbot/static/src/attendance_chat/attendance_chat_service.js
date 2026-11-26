/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { AttendanceChat } from "./attendance_chat";

export const attendanceChatHubService = {
    start() {
        const info = session.attendance_chatbot || {};
        if (!info.eligible) {
            return;
        }
        registry.category("main_components").add(
            "hr_attendance_chatbot.AttendanceChat",
            { Component: AttendanceChat },
            { sequence: 50 },
        );
    },
};

registry.category("services").add("hr_attendance_chatbot.hub", attendanceChatHubService);