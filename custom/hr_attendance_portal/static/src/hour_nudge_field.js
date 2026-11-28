/** @odoo-module **/

import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * In-form ± hour buttons. Must not call type="object": Odoo 18 treats a
 * non-object RPC result as ir.actions.act_window_close and dismisses the wizard.
 */
export class HourNudgeField extends Component {
    static template = "hr_attendance_portal.HourNudgeField";
    static props = { ...standardFieldProps };

    get minusHalf() {
        return _t("-0.5h");
    }
    get minusOne() {
        return _t("-1h");
    }
    get plusHalf() {
        return _t("+0.5h");
    }
    get plusOne() {
        return _t("+1h");
    }

    async onNudge(delta) {
        const record = this.props.record;
        const elapsed = record.data.elapsed_hours || 0;
        let hours = (record.data.recognized_hours || 0) + delta;
        if (hours < 0) {
            hours = 0;
        }
        if (elapsed && hours > elapsed) {
            hours = elapsed;
        }
        await record.update({
            adjustment_mode: "recognized",
            recognized_hours: hours,
        });
    }
}

export const hourNudgeField = {
    component: HourNudgeField,
    supportedTypes: ["float"],
};

registry.category("fields").add("kv_hour_nudge", hourNudgeField);
