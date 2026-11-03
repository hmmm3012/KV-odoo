# -*- coding: utf-8 -*-

"""Overlay employee data on the official 1-page PDF form (same approach as contracts).

LibreOffice DOCX→PDF reflows fonts/spacing and can spill onto page 2. Overlaying
keeps the exact template layout.
"""

import base64
import logging
import tempfile
from io import BytesIO
from pathlib import Path

from pdfrw import PageMerge, PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_logger = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).resolve().parent.parent
_TEMPLATE_PDF = _MODULE_DIR / "static" / "report" / "giay_gioi_thieu_nhan_su.pdf"
_REPO_ROOT = _MODULE_DIR.parent.parent
_FONT_DIR = _REPO_ROOT / "utils" / "font" / "times-new-roman-pdf"
_FALLBACK_FONT_DIR = _REPO_ROOT / "utils" / "font" / "font-times-new-roman"
_FONTS_REGISTERED = False

_FONT = "kv_intro_tiro"
_FONT_BOLD = "kv_intro_tiro_bold"
_PAGE_H = A4[1]
_SIZE = 12

# Measured from blank form (pdftotext -bbox). y nudged +3pt so ReportLab baseline matches labels.
_Y = 3.0
_POS = {
    "recipient": (121.2, 160.5 + _Y),
    "name": (127.8, 270.9 + _Y),
    "gender_male_x": (322.0, 270.9 + _Y),
    "gender_female_x": (452.0, 270.9 + _Y),
    "birthday": (129.4, 299.3 + _Y),
    "place_of_origin": (363.7, 299.3 + _Y),
    "identification_id": (126.6, 327.7 + _Y),
    "identification_date": (368.0, 327.7 + _Y),
    "identification_by": (495.3, 327.7 + _Y),
    "education_level": (166.8, 356.1 + _Y),
    "permanent_address": (174.0, 384.5 + _Y),
    "temporary_address": (156.8, 412.9 + _Y),
    "phone": (170.8, 441.3 + _Y),
    "date_import": (192.4, 469.7 + _Y),
    "job_title": (349.9, 469.7 + _Y),
    "emp_code": (113.8, 498.1 + _Y),
    "work_shift": (382.3, 498.1 + _Y),
    "health_status": (182.0, 526.5 + _Y),
    "sign_line": (326.5, 761.0 + _Y),
}

_PHOTO = {"x": 480.66, "y": 664.78, "w": 93.06, "h": 119.04}


def build_intro_letter_pdf(wizard):
    _register_fonts()
    values = wizard._letter_values()
    if not _TEMPLATE_PDF.is_file():
        raise FileNotFoundError(f"Missing introduction letter PDF: {_TEMPLATE_PDF}")

    overlay = BytesIO()
    c = canvas.Canvas(overlay, pagesize=A4)
    _draw_fields(c, values)
    _draw_photo(c, wizard.employee_id)
    c.showPage()
    c.save()

    with tempfile.TemporaryDirectory(prefix="kv_intro_pdf_") as tmp:
        tmp_path = Path(tmp)
        overlay_path = tmp_path / "overlay.pdf"
        output_path = tmp_path / "output.pdf"
        overlay_path.write_bytes(overlay.getvalue())
        _merge_overlay(_TEMPLATE_PDF, overlay_path, output_path)
        return output_path.read_bytes()


def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    regular = _FONT_DIR / "TimesNewRoman-Regular.ttf"
    bold = _FONT_DIR / "TimesNewRoman-Bold.ttf"
    if not regular.is_file():
        regular = _FALLBACK_FONT_DIR / "SVN-TimesNewRoman.ttf"
        bold = _FALLBACK_FONT_DIR / "SVN-Times New Roman Bold.ttf"
    pdfmetrics.registerFont(TTFont(_FONT, str(regular)))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(bold)))
    _FONTS_REGISTERED = True


def _draw_fields(c, values):
    _text(c, values.get("recipient"), *_POS["recipient"], bold=True, max_width=350)
    _text(c, values.get("name"), *_POS["name"], max_width=180)
    if values.get("gender") == "female":
        _text(c, "X", *_POS["gender_female_x"], bold=True)
    else:
        _text(c, "X", *_POS["gender_male_x"], bold=True)

    _text(c, values.get("birthday"), *_POS["birthday"])
    _text(c, values.get("place_of_origin"), *_POS["place_of_origin"], max_width=120)
    _text(c, values.get("identification_id"), *_POS["identification_id"])
    _text(c, values.get("identification_date"), *_POS["identification_date"])
    _text(c, values.get("identification_by"), *_POS["identification_by"], max_width=70)
    _text(c, values.get("education_level"), *_POS["education_level"], max_width=250)
    _text(c, values.get("permanent_address"), *_POS["permanent_address"], max_width=340)
    _text(c, values.get("temporary_address"), *_POS["temporary_address"], max_width=355)
    _text(c, values.get("phone"), *_POS["phone"])
    _text(c, values.get("date_import"), *_POS["date_import"])
    _text(c, values.get("job_title"), *_POS["job_title"], max_width=170)
    _text(c, values.get("emp_code"), *_POS["emp_code"])
    _text(c, values.get("work_shift"), *_POS["work_shift"], max_width=140)

    health = (values.get("health_status") or "").rstrip(".")
    if health:
        _text(c, f"{health}.", *_POS["health_status"], max_width=320)

    sign = (
        f"Tp.HCM, ngày {values.get('sign_day') or '…..'} "
        f"tháng {values.get('sign_month') or '…..'} "
        f"năm {values.get('sign_year') or '………'}"
    )
    _text(c, sign, *_POS["sign_line"])


def _draw_photo(c, employee):
    raw = employee.with_context(bin_size=False).image_1920 if employee else False
    if not raw:
        return
    try:
        image = ImageReader(BytesIO(base64.b64decode(raw)))
        c.setFillColorRGB(1, 1, 1)
        c.rect(_PHOTO["x"], _PHOTO["y"], _PHOTO["w"], _PHOTO["h"], stroke=0, fill=1)
        c.drawImage(
            image,
            _PHOTO["x"],
            _PHOTO["y"],
            width=_PHOTO["w"],
            height=_PHOTO["h"],
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    except Exception:
        _logger.exception("Could not draw employee photo on introduction letter.")


def _text(c, text, x, y_from_top, bold=False, max_width=None):
    text = text or ""
    if not text:
        return
    font = _FONT_BOLD if bold else _FONT
    c.setFillColorRGB(0, 0, 0)
    c.setFont(font, _SIZE)
    if max_width and c.stringWidth(text, font, _SIZE) > max_width:
        text = _fit_text(c, text, font, _SIZE, max_width)
    c.drawString(x, _PAGE_H - y_from_top, text)


def _fit_text(c, text, font, size, max_width):
    if c.stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "…"
    keep = text
    while keep and c.stringWidth(keep + ellipsis, font, size) > max_width:
        keep = keep[:-1]
    return (keep + ellipsis) if keep else ellipsis


def _merge_overlay(base_pdf, overlay_pdf, output_pdf):
    base_page = PdfReader(str(base_pdf)).pages[0]
    overlay_page = PdfReader(str(overlay_pdf)).pages[0]
    PageMerge(base_page).add(overlay_page).render()
    writer = PdfWriter()
    writer.addpage(base_page)
    writer.write(str(output_pdf))
