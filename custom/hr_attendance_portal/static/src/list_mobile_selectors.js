/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

/**
 * Odoo hides list checkboxes on small screens. Captains reviewing attendance on
 * phones need them when the list exposes bulk header actions (approve overtime,
 * request time correction, etc.).
 */
patch(ListRenderer.prototype, {
    get hasSelectors() {
        if (
            this.props.allowSelectors &&
            this.env.isSmall &&
            this.props.archInfo?.headerButtons?.length
        ) {
            return true;
        }
        return super.hasSelectors;
    },
});
