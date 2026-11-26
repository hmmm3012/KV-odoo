"""Load Vietnamese override terms for official HR UI strings.

Official hr/hr_skills/hr_homeworking/hr_attendance vi.po is stale or has
wrong terms (e.g. Create User -> "Người tạo", Resume -> "Tiếp tục").
This hook imports custom/hr_employee_kv/i18n/vi.po with force_overwrite
so those jsonb vi_VN values are updated without patching Odoo core.
"""
import logging

from odoo.tools.misc import file_path
from odoo.tools.translate import TranslationImporter

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    po_path = file_path("hr_employee_kv/i18n/vi.po")
    importer = TranslationImporter(cr, verbose=True)
    importer.load_file(po_path, "vi_VN")
    importer.save(overwrite=True, force_overwrite=True)
    _logger.info("hr_employee_kv: loaded Vietnamese HR UI overrides from %s", po_path)
