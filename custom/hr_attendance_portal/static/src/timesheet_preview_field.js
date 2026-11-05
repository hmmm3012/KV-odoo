/** @odoo-module **/

import { Component, markup, useEffect, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

function enableDragScroll(element) {
    let pointerId = null;
    let startX = 0;
    let startY = 0;
    let scrollLeft = 0;
    let scrollTop = 0;
    let dragging = false;
    let moved = false;

    const onPointerDown = (event) => {
        if (event.pointerType === "mouse" && event.button !== 0) {
            return;
        }
        if (event.target.closest("a, button, input, textarea, select, label, .kv-drag-handle")) {
            return;
        }
        pointerId = event.pointerId;
        startX = event.clientX;
        startY = event.clientY;
        scrollLeft = element.scrollLeft;
        scrollTop = element.scrollTop;
        dragging = true;
        moved = false;
        element.classList.add("is-dragging");
        element.setPointerCapture?.(pointerId);
    };

    const onPointerMove = (event) => {
        if (!dragging || event.pointerId !== pointerId) {
            return;
        }
        const deltaX = event.clientX - startX;
        const deltaY = event.clientY - startY;
        if (!moved && Math.abs(deltaX) + Math.abs(deltaY) < 3) {
            return;
        }
        moved = true;
        element.scrollLeft = scrollLeft - deltaX;
        element.scrollTop = scrollTop - deltaY;
        event.preventDefault();
    };

    const onPointerUp = (event) => {
        if (event.pointerId !== pointerId) {
            return;
        }
        dragging = false;
        pointerId = null;
        element.classList.remove("is-dragging");
    };

    const onClickCapture = (event) => {
        if (!moved) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        moved = false;
    };

    element.addEventListener("pointerdown", onPointerDown);
    element.addEventListener("pointermove", onPointerMove);
    element.addEventListener("pointerup", onPointerUp);
    element.addEventListener("pointercancel", onPointerUp);
    element.addEventListener("click", onClickCapture, true);

    return () => {
        element.removeEventListener("pointerdown", onPointerDown);
        element.removeEventListener("pointermove", onPointerMove);
        element.removeEventListener("pointerup", onPointerUp);
        element.removeEventListener("pointercancel", onPointerUp);
        element.removeEventListener("click", onClickCapture, true);
        element.classList.remove("is-dragging");
    };
}

function sectionPersonRows(tbody, section) {
    return Array.from(tbody.querySelectorAll(`tr.kv-person[data-section="${section}"]`));
}

function renumberSection(tbody, section) {
    sectionPersonRows(tbody, section).forEach((row, index) => {
        const indexEl = row.querySelector(".kv-row-index");
        if (indexEl) {
            indexEl.textContent = String(index + 1);
        }
    });
}

function rowFromPoint(clientX, clientY, section) {
    const stack = document.elementsFromPoint?.(clientX, clientY) || [];
    for (const el of stack) {
        const row = el.closest?.("tr.kv-person");
        if (row && row.dataset.section === section) {
            return row;
        }
    }
    const fallback = document.elementFromPoint(clientX, clientY)?.closest?.("tr.kv-person");
    if (fallback && fallback.dataset.section === section) {
        return fallback;
    }
    return null;
}

function enableRowReorder(root, { onReorder, onReset }) {
    const wrap = root.querySelector(".kv-timesheet-wrap");
    const tbody = root.querySelector(".kv-timesheet tbody");
    if (!wrap || !tbody) {
        return () => {};
    }

    const departmentId = Number(wrap.dataset.departmentId || 0);
    let dragRow = null;
    let pointerId = null;
    let moved = false;
    let saving = false;

    const setStatus = (message, isError = false) => {
        const statusEl = root.querySelector(".kv-timesheet-order-status");
        if (!statusEl) {
            return;
        }
        statusEl.textContent = message || "";
        statusEl.classList.toggle("is-error", Boolean(isError));
    };

    const finishReorder = async () => {
        if (!dragRow) {
            return;
        }
        const section = dragRow.dataset.section;
        const row = dragRow;
        row.classList.remove("is-row-dragging");
        tbody.querySelectorAll(".kv-person.is-drop-target").forEach((item) => {
            item.classList.remove("is-drop-target");
        });
        dragRow = null;
        pointerId = null;

        if (!moved || !section) {
            return;
        }
        renumberSection(tbody, section);
        const employeeIds = sectionPersonRows(tbody, section)
            .map((item) => Number(item.dataset.employeeId))
            .filter((employeeId) => employeeId > 0);
        if (!departmentId || !employeeIds.length || saving) {
            setStatus(
                departmentId ? "Không lưu được thứ tự." : "Thiếu bãi xe trên bảng công.",
                true
            );
            return;
        }
        saving = true;
        setStatus("Đang lưu thứ tự…");
        try {
            await onReorder(departmentId, employeeIds);
            setStatus("Đã lưu thứ tự");
        } catch (error) {
            setStatus(
                error?.data?.message || error?.message || "Không lưu được thứ tự.",
                true
            );
        } finally {
            saving = false;
        }
    };

    const onPointerDown = (event) => {
        if (event.pointerType === "mouse" && event.button !== 0) {
            return;
        }
        const handle = event.target.closest(".kv-drag-handle");
        if (!handle) {
            return;
        }
        const row = handle.closest("tr.kv-person");
        if (!row) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        dragRow = row;
        pointerId = event.pointerId;
        moved = false;
        row.classList.add("is-row-dragging");
        handle.setPointerCapture?.(event.pointerId);
    };

    const onPointerMove = (event) => {
        if (!dragRow || event.pointerId !== pointerId) {
            return;
        }
        event.preventDefault();
        const section = dragRow.dataset.section;
        const target = rowFromPoint(event.clientX, event.clientY, section);
        if (!target || target === dragRow) {
            return;
        }
        const rect = target.getBoundingClientRect();
        const before = event.clientY < rect.top + rect.height / 2;
        const reference = before ? target : target.nextSibling;
        if (reference === dragRow || dragRow.nextSibling === reference) {
            return;
        }
        tbody.querySelectorAll(".kv-person.is-drop-target").forEach((item) => {
            item.classList.remove("is-drop-target");
        });
        target.classList.add("is-drop-target");
        tbody.insertBefore(dragRow, reference);
        moved = true;
        renumberSection(tbody, section);
    };

    const onPointerUp = (event) => {
        if (event.pointerId !== pointerId) {
            return;
        }
        finishReorder();
    };

    const onResetClick = async (event) => {
        const button = event.target.closest(".kv-timesheet-reset-order");
        if (!button || saving) {
            return;
        }
        saving = true;
        setStatus("Đang đặt lại thứ tự…");
        try {
            await onReset();
            setStatus("Đã đặt lại thứ tự A→Z");
        } catch (error) {
            setStatus(
                error?.data?.message || error?.message || "Không đặt lại được thứ tự.",
                true
            );
        } finally {
            saving = false;
        }
    };

    tbody.addEventListener("pointerdown", onPointerDown);
    tbody.addEventListener("pointermove", onPointerMove);
    tbody.addEventListener("pointerup", onPointerUp);
    tbody.addEventListener("pointercancel", onPointerUp);
    root.addEventListener("click", onResetClick);

    return () => {
        tbody.removeEventListener("pointerdown", onPointerDown);
        tbody.removeEventListener("pointermove", onPointerMove);
        tbody.removeEventListener("pointerup", onPointerUp);
        tbody.removeEventListener("pointercancel", onPointerUp);
        root.removeEventListener("click", onResetClick);
        if (dragRow) {
            dragRow.classList.remove("is-row-dragging");
        }
        dragRow = null;
    };
}

export class TimesheetPreviewField extends Component {
    static template = "hr_attendance_portal.TimesheetPreviewField";
    static props = { ...standardFieldProps };

    setup() {
        this.rootRef = useRef("root");
        this.orm = useService("orm");
        useEffect(
            () => {
                const root = this.rootRef.el;
                if (!root) {
                    return;
                }
                const scroller = root.querySelector(".kv-timesheet-scroll");
                const cleanups = [];
                if (scroller) {
                    // Keep horizontal scrolling inside this box so sticky left columns work.
                    scroller.style.width = "100%";
                    scroller.style.maxWidth = "100%";
                    scroller.style.minWidth = "0";
                    cleanups.push(enableDragScroll(scroller));
                }
                cleanups.push(
                    enableRowReorder(root, {
                        onReorder: (departmentId, employeeIds) =>
                            this.orm.call(
                                "hr.attendance.timesheet.wizard",
                                "save_row_order",
                                [departmentId, employeeIds]
                            ),
                        onReset: async () => {
                            const record = this.props.record;
                            if (!record.resId) {
                                throw new Error("Hãy xem bảng công trước.");
                            }
                            await this.orm.call(
                                record.resModel,
                                "action_reset_row_order",
                                [[record.resId]]
                            );
                            await record.load();
                        },
                    })
                );
                return () => {
                    cleanups.forEach((cleanup) => cleanup?.());
                };
            },
            () => [this.props.record.data[this.props.name], this.props.record.resId]
        );
    }

    get hasPreview() {
        const value = this.props.record.data[this.props.name];
        return Boolean(value && String(value).trim());
    }

    get html() {
        const value = this.props.record.data[this.props.name];
        return value ? markup(value) : markup("");
    }
}

export const timesheetPreviewField = {
    component: TimesheetPreviewField,
    displayName: _t("Timesheet Preview"),
    supportedTypes: ["html"],
};

registry.category("fields").add("kv_timesheet_preview", timesheetPreviewField);
