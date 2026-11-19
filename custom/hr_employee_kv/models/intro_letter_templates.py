# -*- coding: utf-8 -*-

"""Per-company introduction letter templates (DOCX/ODT paths and portrait assets)."""

from pathlib import Path

_MODULE_STATIC = Path(__file__).resolve().parent.parent / "static" / "report"

KIEN_VIET = "kien_viet"
THANH_NIEN = "thanh_nien"

INTRO_LETTER_TEMPLATE_SELECTION = [
    (KIEN_VIET, "Mẫu Kiến Việt (mặc định)"),
    (THANH_NIEN, "Mẫu Thanh Niên (SGC)"),
]

INTRO_LETTER_TEMPLATES = {
    KIEN_VIET: {
        "docx": _MODULE_STATIC / "giay_gioi_thieu_nhan_su.docx",
        "odt": _MODULE_STATIC / "giay_gioi_thieu_nhan_su.odt",
        "docx_portrait": "word/media/image2.jpeg",
        "odt_portrait": "media/image2.jpeg",
        "portrait_format": "jpeg",
    },
    THANH_NIEN: {
        "docx": _MODULE_STATIC / "giay_gioi_thieu_thanh_nien.docx",
        "odt": _MODULE_STATIC / "giay_gioi_thieu_thanh_nien.odt",
        "docx_portrait": "word/media/image2.png",
        "odt_portrait": "Pictures/10000001000001AE000000BB96DBD76C.png",
        "portrait_format": "png",
    },
}


def intro_letter_template_key(company):
    key = company.intro_letter_template or KIEN_VIET
    if key not in INTRO_LETTER_TEMPLATES:
        return KIEN_VIET
    return key


def recipient_lines(recipient):
    if not recipient:
        return []
    return [line.strip() for line in str(recipient).splitlines() if line.strip()]


def template_config(template_key):
    return INTRO_LETTER_TEMPLATES[intro_letter_template_key_value(template_key)]


def intro_letter_template_key_value(key):
    return key if key in INTRO_LETTER_TEMPLATES else KIEN_VIET