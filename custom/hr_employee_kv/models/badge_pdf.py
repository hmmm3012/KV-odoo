# -*- coding: utf-8 -*-

"""Employee badge: overlay text and photo on the printer-ready card template.

The template is 100 x 65.3 mm including a 3 mm bleed. Coordinates below are in
points measured from the top-left corner of the template, taken from the
approved sample card.
"""

import base64
import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from pdfrw import PageMerge, PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_logger = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).resolve().parent.parent
_TEMPLATE_PDF = _MODULE_DIR / "static" / "report" / "the_nhan_vien.pdf"
_FONT_DIR = _MODULE_DIR / "static" / "fonts"
_FONTS = {
    "kv_badge_regular": "BeVietnamPro-Regular.ttf",
    "kv_badge_medium": "BeVietnamPro-Medium.ttf",
    "kv_badge_semibold": "BeVietnamPro-SemiBold.ttf",
    "kv_badge_bold": "BeVietnamPro-Bold.ttf",
}
_FONTS_REGISTERED = False

_TEXT_LEFT = 101.2
_TEXT_MAX_WIDTH = 165.0

# key: (font, size, rgb, x, baseline from top, align, tracking in em)
# Negative tracking narrows Be Vietnam Pro to the width of the designer's font.
_STYLE = {
    "name_label": ("kv_badge_regular", 5.0, (94, 40, 5), 100.9, 82.24, "left", 0.0),
    "name": ("kv_badge_bold", 12.0, (31, 23, 12), _TEXT_LEFT, 96.04, "left", -0.026),
    "job": ("kv_badge_bold", 7.5, (31, 23, 12), 101.0, 116.44, "left", -0.02),
    "department": ("kv_badge_regular", 6.2, (65, 33, 8), 101.0, 126.2, "left", 0.0),
    "code_label": ("kv_badge_medium", 5.0, (254, 220, 195), 262.4, 158.44, "right", 0.0),
    "code": ("kv_badge_semibold", 10.0, (255, 255, 255), 262.0, 169.52, "right", -0.017),
}
_RULE = {"x": 100.4, "y": 103.96, "w": 18.71, "h": 0.84, "rgb": (52, 16, 6)}
_PHOTO = {"x": 25.55, "y": 70.78, "w": 59.26, "h": 77.85}
# Photo pixels at ~600 dpi on the card.
_PHOTO_PX = (494, 649)

# Pack badges onto A4 (2 columns × 4 rows = 8 cards per sheet).
_A4 = (595.28, 841.89)
_COLS = 2
_ROWS = 4
_PER_PAGE = _COLS * _ROWS
# White gap between cards so they can be cut apart (≈ 4 mm).
_GAP = 11.34


def build_badge_pdf(cards):
    """Return PDF bytes with up to 8 badges per A4 page.

    Each card has: name, job, department, code, photo (base64 or False).
    """
    if not cards:
        raise ValueError("No badges to print.")
    if not _TEMPLATE_PDF.is_file():
        raise FileNotFoundError(f"Missing employee badge template: {_TEMPLATE_PDF}")
    _register_fonts()

    template = PdfReader(str(_TEMPLATE_PDF)).pages[0]
    card_w, card_h = (float(v) for v in template.MediaBox[2:4])

    overlay = BytesIO()
    c = canvas.Canvas(overlay, pagesize=(card_w, card_h))
    for card in cards:
        _draw_card(c, card, card_h)
        c.showPage()
    c.save()
    overlay.seek(0)
    overlay_pages = PdfReader(overlay).pages

    page_w, page_h = _A4
    step_x = card_w + _GAP
    step_y = card_h + _GAP
    grid_w = _COLS * card_w + (_COLS - 1) * _GAP
    grid_h = _ROWS * card_h + (_ROWS - 1) * _GAP
    margin_x = (page_w - grid_w) / 2
    margin_y = (page_h - grid_h) / 2
    blank_bytes = _blank_a4_bytes()

    writer = PdfWriter()
    for start in range(0, len(overlay_pages), _PER_PAGE):
        sheet = PdfReader(fdata=blank_bytes).pages[0]
        merge = PageMerge(sheet)
        for index, overlay_page in enumerate(overlay_pages[start : start + _PER_PAGE]):
            col = index % _COLS
            row = index // _COLS
            x = margin_x + col * step_x
            y = page_h - margin_y - card_h - row * step_y
            merge.add(template)
            merge[-1].x = x
            merge[-1].y = y
            merge.add(overlay_page)
            merge[-1].x = x
            merge[-1].y = y
        merge.render()
        writer.addpage(sheet)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _blank_a4_bytes():
    buffer = BytesIO()
    blank = canvas.Canvas(buffer, pagesize=_A4)
    blank.showPage()
    blank.save()
    return buffer.getvalue()


def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    for name, filename in _FONTS.items():
        pdfmetrics.registerFont(TTFont(name, str(_FONT_DIR / filename)))
    _FONTS_REGISTERED = True


def _draw_card(c, card, page_h):
    _draw_photo(c, card.get("photo"), page_h)

    _text(c, "HỌ VÀ TÊN", "name_label", page_h)
    _text(c, (card.get("name") or "").upper(), "name", page_h)

    r, g, b = _RULE["rgb"]
    c.setFillColorRGB(r / 255, g / 255, b / 255)
    c.rect(_RULE["x"], page_h - _RULE["y"] - _RULE["h"], _RULE["w"], _RULE["h"], stroke=0, fill=1)

    _text(c, (card.get("job") or "").upper(), "job", page_h, max_width=_TEXT_MAX_WIDTH)
    department = card.get("department") or ""
    if department:
        _text(c, f"Bộ phận: {department}", "department", page_h, max_width=_TEXT_MAX_WIDTH)

    _text(c, "MÃ NV", "code_label", page_h)
    _text(c, card.get("code") or "", "code", page_h)


def _text(c, text, style, page_h, max_width=None):
    if not text:
        return
    font, size, rgb, x, baseline, align, tracking = _STYLE[style]
    width = _text_width(text, font, size, tracking)
    if max_width and width > max_width:
        size = size * max_width / width
        width = max_width
    if align == "right":
        x -= width
    t = c.beginText(x, page_h - baseline)
    t.setFont(font, size)
    t.setCharSpace(tracking * size)
    t.setFillColorRGB(*(v / 255 for v in rgb))
    t.textOut(text)
    c.drawText(t)


def _text_width(text, font, size, tracking):
    return pdfmetrics.stringWidth(text, font, size) + tracking * size * (len(text) - 1)


def _draw_photo(c, photo, page_h):
    if not photo:
        return
    try:
        image = _cover_crop(base64.b64decode(photo))
    except Exception:
        _logger.exception("Could not read employee photo for badge.")
        return
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    buffer.seek(0)
    c.drawImage(
        ImageReader(buffer),
        _PHOTO["x"],
        page_h - _PHOTO["y"] - _PHOTO["h"],
        width=_PHOTO["w"],
        height=_PHOTO["h"],
    )


def _cover_crop(raw):
    """Crop to the frame ratio so the photo fills it; keep faces near the top."""
    image = ImageOps.exif_transpose(Image.open(BytesIO(raw)))
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        image = background
    else:
        image = image.convert("RGB")

    target_ratio = _PHOTO["w"] / _PHOTO["h"]
    width, height = image.size
    if width / height > target_ratio:
        new_width = round(height * target_ratio)
        left = (width - new_width) // 2
        box = (left, 0, left + new_width, height)
    else:
        new_height = round(width / target_ratio)
        top = round((height - new_height) * 0.25)
        box = (0, top, width, top + new_height)
    image = image.crop(box)
    if image.width > _PHOTO_PX[0]:
        image = image.resize(_PHOTO_PX, Image.LANCZOS)
    return image
