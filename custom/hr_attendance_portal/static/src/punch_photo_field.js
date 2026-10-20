/** @odoo-module **/

import { ImageField, imageField } from "@web/views/fields/image/image_field";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { registry } from "@web/core/registry";

export class PunchPhotoField extends ImageField {
    static template = "hr_attendance_portal.PunchPhotoField";

    setup() {
        super.setup();
        this.fileViewer = useFileViewer();
    }

    onPunchPhotoClick() {
        if (!this.props.record.data[this.props.name] || !this.state.isValid) {
            return;
        }
        const url = this.getUrl(this.props.previewImage || this.props.name);
        this.fileViewer.open({
            displayName: this.imgAlt || "Punch photo",
            downloadUrl: url,
            defaultSource: url,
            isImage: true,
            isViewable: true,
        });
    }
}

export const punchPhotoField = {
    ...imageField,
    component: PunchPhotoField,
};

registry.category("fields").add("punch_photo", punchPhotoField);
