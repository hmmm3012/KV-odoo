/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MODEL = "hr.department.off";
const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const SHIFTS = [
    { shift: "day", title: "Ca ngày", other: "night" },
    { shift: "night", title: "Ca đêm", other: "day" },
];
const MAX_CHIPS = 3;

function pad(value) {
    return String(value).padStart(2, "0");
}

function fold(text) {
    return (text || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/đ/gi, "d")
        .toLowerCase()
        .trim();
}

function shortNames(employees) {
    const lastWord = (name) => (name || "").trim().split(/\s+/).pop();
    const counts = {};
    for (const employee of employees) {
        const key = lastWord(employee.name);
        counts[key] = (counts[key] || 0) + 1;
    }
    const labels = {};
    for (const employee of employees) {
        const words = (employee.name || "").trim().split(/\s+/);
        labels[employee.id] = counts[lastWord(employee.name)] > 1 ? words.slice(-2).join(" ") : words.pop();
    }
    return labels;
}

export class OffCalendar extends Component {
    static template = "hr_attendance_portal.OffCalendar";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.weekdays = WEEKDAYS;
        this.employees = {};
        this.labels = {};
        const today = new Date();
        this.state = useState({
            departments: [],
            departmentId: false,
            year: today.getFullYear(),
            month: today.getMonth() + 1,
            data: null,
            offs: {},
            selected: null,
            search: "",
            dirty: false,
            saving: false,
        });
        useBus(this.env.bus, "CLEAR-UNCOMMITTED-CHANGES", (ev) => {
            if (this.state.dirty) {
                ev.detail.push(() => this.confirmDiscard());
            }
        });
        useSetupAction({
            beforeUnload: (ev) => {
                if (this.state.dirty) {
                    ev.preventDefault();
                    ev.returnValue = "";
                }
            },
        });
        onWillStart(async () => {
            this.state.departments = await this.orm.call(MODEL, "off_calendar_departments", []);
            const wanted = (this.props.action.context || {}).default_department_id;
            const department =
                this.state.departments.find((item) => item.id === wanted) || this.state.departments[0];
            if (department) {
                this.state.departmentId = department.id;
                await this.load();
            }
        });
    }

    async load() {
        const data = await this.orm.call(MODEL, "off_calendar_load", [
            this.state.departmentId,
            this.state.year,
            this.state.month,
        ]);
        this.applyData(data);
    }

    applyData(data, keepSelection = false) {
        this.employees = Object.fromEntries(data.employees.map((employee) => [employee.id, employee]));
        this.labels = shortNames(data.employees);
        const offs = {};
        for (const [key, value] of Object.entries(data.offs)) {
            offs[key] = { day: [...value.day], night: [...value.night] };
        }
        const prefix = `${data.year}-${pad(data.month)}-`;
        const selected = keepSelection && this.state.selected?.startsWith(prefix) ? this.state.selected : null;
        this.state.data = data;
        this.state.offs = offs;
        this.state.dirty = false;
        this.state.selected = selected || (data.today.startsWith(prefix) ? data.today : `${prefix}01`);
    }

    confirmDiscard() {
        return new Promise((resolve) => {
            this.dialog.add(
                ConfirmationDialog,
                {
                    title: "Lịch OFF chưa lưu",
                    body: "Bạn có thay đổi chưa lưu. Bỏ các thay đổi này?",
                    confirmLabel: "Bỏ thay đổi",
                    cancelLabel: "Ở lại",
                    confirm: () => resolve(true),
                    cancel: () => resolve(false),
                },
                { onClose: () => resolve(false) }
            );
        });
    }

    async leaveIfAllowed() {
        return !this.state.dirty || (await this.confirmDiscard());
    }

    async onDepartmentChange(ev) {
        const departmentId = parseInt(ev.target.value);
        if (!(await this.leaveIfAllowed())) {
            ev.target.value = this.state.departmentId;
            return;
        }
        this.state.departmentId = departmentId;
        this.state.search = "";
        await this.load();
    }

    async changeMonth(delta) {
        if (!(await this.leaveIfAllowed())) {
            return;
        }
        const index = this.state.year * 12 + (this.state.month - 1) + delta;
        this.state.year = Math.floor(index / 12);
        this.state.month = (index % 12) + 1;
        await this.load();
    }

    async goToCurrentMonth() {
        const today = new Date();
        const delta =
            today.getFullYear() * 12 + today.getMonth() - (this.state.year * 12 + this.state.month - 1);
        if (delta) {
            await this.changeMonth(delta);
        }
    }

    selectDay(key) {
        this.state.selected = key;
    }

    get readonly() {
        const lock = this.state.data?.lock;
        return Boolean(lock?.locked && !lock.is_hr);
    }

    get lockNotice() {
        const lock = this.state.data?.lock;
        if (!lock) {
            return null;
        }
        const formatDate = (value) => value.split("-").reverse().join("/");
        const month = `${pad(this.state.month)}/${this.state.year}`;
        if (!lock.locked) {
            return {
                cls: "alert-light",
                text: `Đội trưởng chỉnh sửa lịch OFF tháng ${month} được đến hết ngày ${formatDate(lock.last_day)}.`,
            };
        }
        if (lock.is_hr) {
            return {
                cls: "alert-info",
                text: `Lịch OFF tháng ${month} đã chốt với đội trưởng từ ngày ${formatDate(lock.date)}. Bạn đang chỉnh sửa với quyền nhân sự.`,
            };
        }
        return {
            cls: "alert-warning",
            text: `Lịch OFF tháng ${month} đã chốt từ ngày ${formatDate(lock.date)}. Chỉ nhân sự được chỉnh sửa.`,
        };
    }

    toggle(employeeId, shift) {
        if (this.readonly) {
            return;
        }
        const key = this.state.selected;
        const other = shift === "day" ? "night" : "day";
        const entry = this.state.offs[key] || { day: [], night: [] };
        if (entry[shift].includes(employeeId)) {
            entry[shift] = entry[shift].filter((id) => id !== employeeId);
        } else {
            entry[shift] = [...entry[shift], employeeId];
            entry[other] = entry[other].filter((id) => id !== employeeId);
        }
        this.state.offs[key] = entry;
        this.state.dirty = true;
    }

    discard() {
        this.applyData(this.state.data, true);
    }

    async save() {
        this.state.saving = true;
        try {
            const data = await this.orm.call(MODEL, "off_calendar_save", [
                this.state.departmentId,
                this.state.year,
                this.state.month,
                this.state.offs,
            ]);
            this.applyData(data, true);
            this.notification.add("Đã lưu lịch OFF.", { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    get monthLabel() {
        return `Tháng ${this.state.month}/${this.state.year}`;
    }

    get limits() {
        return this.state.data?.limits || { day: 0, night: 0 };
    }

    get limitLabel() {
        const { day, night } = this.limits;
        const text = (value) => (value ? `${value}` : "không giới hạn");
        return `OFF tối đa mỗi ngày: ca ngày ${text(day)}, ca đêm ${text(night)}`;
    }

    entry(key) {
        return this.state.offs[key] || { day: [], night: [] };
    }

    isOver(key, shift) {
        const limit = this.limits[shift];
        return Boolean(limit) && this.entry(key)[shift].length > limit;
    }

    get cells() {
        const data = this.state.data;
        if (!data) {
            return [];
        }
        const cells = [];
        for (let index = 0; index < data.first_weekday; index++) {
            cells.push({ key: `blank-${index}`, blank: true });
        }
        for (let day = 1; day <= data.days_in_month; day++) {
            const key = `${data.year}-${pad(data.month)}-${pad(day)}`;
            const entry = this.entry(key);
            const weekday = (data.first_weekday + day - 1) % 7;
            const chips = [];
            for (const { shift } of SHIFTS) {
                for (const id of entry[shift].slice(0, MAX_CHIPS)) {
                    chips.push({
                        key: `${shift}-${id}`,
                        label: this.labels[id] || "?",
                        title: this.employees[id]?.name || "",
                        cls: `kv-off-chip-${shift}`,
                    });
                }
                if (entry[shift].length > MAX_CHIPS) {
                    chips.push({
                        key: `${shift}-more`,
                        label: `+${entry[shift].length - MAX_CHIPS}`,
                        title: entry[shift].slice(MAX_CHIPS).map((id) => this.employees[id]?.name).join(", "),
                        cls: `kv-off-chip-${shift} kv-off-chip-more`,
                    });
                }
            }
            const overDay = this.isOver(key, "day");
            const overNight = this.isOver(key, "night");
            cells.push({
                key,
                day,
                weekday,
                chips,
                dayCount: entry.day.length,
                nightCount: entry.night.length,
                overDay,
                overNight,
                isToday: key === data.today,
                isPast: key < data.today,
                ariaLabel:
                    `${WEEKDAYS[weekday]} ${day}/${data.month}: ${entry.day.length} người OFF ca ngày, ` +
                    `${entry.night.length} người OFF ca đêm${overDay || overNight ? ", vượt mức tối đa" : ""}`,
            });
        }
        return cells;
    }

    get selectedLabel() {
        const key = this.state.selected;
        if (!key) {
            return "";
        }
        const [year, month, day] = key.split("-").map(Number);
        const weekday = (new Date(year, month - 1, day).getDay() + 6) % 7;
        return `${WEEKDAYS[weekday]}, ${pad(day)}/${pad(month)}/${year}`;
    }

    get panels() {
        const key = this.state.selected;
        const entry = this.entry(key);
        const query = fold(this.state.search);
        const employees = this.state.data?.employees || [];
        return SHIFTS.map(({ shift, title, other }) => {
            const chosen = entry[shift];
            const limit = this.limits[shift];
            const people = employees
                .filter(
                    (employee) =>
                        chosen.includes(employee.id) || !employee.shift || employee.shift === shift
                )
                .filter((employee) => !query || fold(employee.name).includes(query))
                .map((employee) => {
                    let note = "";
                    if (entry[other].includes(employee.id)) {
                        note = other === "day" ? "đang OFF ca ngày" : "đang OFF ca đêm";
                    } else if (!employee.shift) {
                        note = "chưa xếp ca";
                    }
                    return { id: employee.id, name: employee.name, checked: chosen.includes(employee.id), note };
                })
                .sort((a, b) => Number(b.checked) - Number(a.checked));
            return {
                shift,
                title,
                people,
                over: this.isOver(key, shift),
                countLabel: limit ? `${chosen.length}/${limit}` : `${chosen.length}`,
            };
        });
    }
}

registry.category("actions").add("hr_attendance_portal.off_calendar", OffCalendar);
