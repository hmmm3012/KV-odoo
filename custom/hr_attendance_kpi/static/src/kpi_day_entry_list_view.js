/** @odoo-module **/

import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { onMounted } from "@odoo/owl";

export class KpiDayEntryListController extends ListController {
    setup() {
        super.setup();
        onMounted(() => {
            const addBtn = this.rootRef?.el?.querySelector(".o_list_button_add");
            if (addBtn) {
                addBtn.textContent = _t("Thêm");
            }
        });
    }

    get display() {
        const display = super.display;
        if (!display.controlPanel) {
            return display;
        }
        return {
            ...display,
            controlPanel: {
                ...display.controlPanel,
                layoutActions: false,
            },
        };
    }
}

export const kpiDayEntryListView = {
    ...listView,
    searchMenuTypes: [],
    Controller: KpiDayEntryListController,
};

registry.category("views").add("kpi_day_entry_list", kpiDayEntryListView);