/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { VersionsTimeline } from "@hr/components/versions_timeline/versions_timeline";

patch(VersionsTimeline.prototype, {
    /**
     * Title of the "+" button that opens the date picker to create a new
     * hr.version. Translated here because Odoo only loads JS terms from the
     * originating module's i18n/*.po (hr), not from a custom override po.
     */
    get newRecordTitle() {
        return _t("New Employee Record");
    },

    /** @override */
    getAllItems() {
        const items = super.getAllItems();
        if (!this.displayContractLines) {
            return items;
        }
        return items.map((item) => {
            if (!item.isInContract) {
                return { ...item, toolTip: _t("No contract") };
            }
            return item;
        });
    },
});
