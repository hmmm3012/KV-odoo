/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

const FROM_RECORD = "FROM_RECORD";

function imageArg(value) {
    if (!value) {
        return false;
    }
    if (typeof value === "string") {
        const trimmed = value.trim();
        if (/^\d+(\.\d+)?\s*(bytes?|kB|KB|Kb|MB|Mb|GB|Gb)$/i.test(trimmed)) {
            return FROM_RECORD;
        }
        if (trimmed.length > 80) {
            return trimmed;
        }
        return FROM_RECORD;
    }
    return FROM_RECORD;
}

export class IdCardAutofillWidget extends Component {
    static template = "hr_employee_kv.IdCardAutofill";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ busy: false });
    }

    async onClick() {
        if (this.state.busy || this.props.readonly) {
            return;
        }
        this.state.busy = true;
        try {
            const data = this.props.record.data;
            const result = await this.orm.call("hr.employee", "read_id_card_from_images", [], {
                front: imageArg(data.id_card_front),
                back: imageArg(data.id_card_back),
                employee_id: this.props.record.resId || false,
            });
            if (result.ok && result.values) {
                await this.props.record.update(result.values);
            }
            this.notification.add(result.message, {
                title: result.title || _t("Tự nhập thông tin"),
                type: result.notification_type || "warning",
            });
        } catch (error) {
            const message =
                (error && error.data && error.data.message) ||
                (error && error.message) ||
                _t("Không đọc được ảnh CCCD. Vui lòng thử lại.");
            this.notification.add(message, {
                title: _t("Tự nhập thông tin"),
                type: "danger",
            });
        } finally {
            this.state.busy = false;
        }
    }
}

export const idCardAutofillWidget = {
    component: IdCardAutofillWidget,
    fieldDependencies: [
        { name: "id_card_front", type: "binary" },
        { name: "id_card_back", type: "binary" },
    ],
};

registry.category("view_widgets").add("kv_id_card_autofill", idCardAutofillWidget);
