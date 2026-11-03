# -*- coding: utf-8 -*-

"""Fill the official Word template by editing XML in-place.

python-docx rewrite destroys headers/drawings/styles. Instead we copy the
template ZIP and only change <w:t> text nodes (and optionally the portrait).
"""

import io
import zipfile
from pathlib import Path

from lxml import etree
from odoo.exceptions import UserError

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "static"
    / "report"
    / "giay_gioi_thieu_nhan_su.docx"
)
PORTRAIT_NAME = "word/media/image2.jpeg"
PORTRAIT_SIZE = (244, 326)


def build_intro_letter_docx(wizard):
    values = wizard._letter_values()
    if not TEMPLATE_PATH.is_file():
        raise UserError(
            wizard.env._("Thiếu file mẫu giấy giới thiệu nhân sự trên hệ thống.")
        )

    portrait_jpeg = _employee_portrait_jpeg(wizard.employee_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(TEMPLATE_PATH, "r") as src, zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "word/document.xml":
                data = _fill_document_xml(data, values)
            elif info.filename == PORTRAIT_NAME and portrait_jpeg:
                data = portrait_jpeg
            # Keep original compress type for already-stored media when possible.
            if info.filename.endswith((".png", ".jpeg", ".jpg")):
                dst.writestr(info, data, compress_type=zipfile.ZIP_STORED)
            else:
                dst.writestr(info.filename, data)
    return buffer.getvalue()


def _fill_document_xml(xml_bytes, values):
    root = etree.fromstring(xml_bytes)
    male = values.get("gender") == "male"
    female = values.get("gender") == "female"
    # If gender unknown, keep sample mark on Nam (matches blank form usage).
    if not male and not female:
        male = True

    day_dots_done = False
    for paragraph in root.iter(f"{W}p"):
        full = _paragraph_text(paragraph)
        if not full:
            continue

        if full.startswith("Kính gửi:"):
            _set_text_node(paragraph, 1, values.get("recipient") or "…………………………….")
        elif full.startswith("Họ và tên"):
            _set_text_node(paragraph, 2, values.get("name") or "")
        elif "Nam" in full and "Nữ" not in full:
            _set_gender_male_paragraph(paragraph, selected=male)
        elif "Nữ" in full and "Nam" not in full:
            _set_gender_female_paragraph(paragraph, selected=female)
        elif full.startswith("Ngày sinh"):
            _set_text_node(paragraph, 2, values.get("birthday") or "")
        elif full.startswith("Nơi sinh"):
            place = values.get("place_of_origin") or ""
            _set_text_node(paragraph, 1, f" {place}" if place else " ")
        elif full.startswith("CCCD số"):
            _set_text_node(paragraph, 3, values.get("identification_id") or "")
        elif full.startswith("Ngày cấp"):
            _set_text_node(paragraph, 1, values.get("identification_date") or "")
        elif full.startswith("Nơi cấp"):
            _set_text_node(paragraph, 1, values.get("identification_by") or "")
        elif full.startswith("Trình độ học vấn"):
            _set_text_node(paragraph, 2, values.get("education_level") or "")
        elif full.startswith("Địa chỉ thường trú"):
            _set_text_node(paragraph, 3, values.get("permanent_address") or "")
        elif full.startswith("Địa chỉ tạm trú"):
            _set_text_node(paragraph, 2, values.get("temporary_address") or "")
        elif full.startswith("Điện thoại liên lạc"):
            _set_text_node(paragraph, 2, values.get("phone") or "")
        elif full.startswith("Ngày bắt đầu làm việc"):
            _set_text_node(paragraph, 2, values.get("date_import") or "")
        elif full.startswith("Vị trí"):
            _set_text_node(paragraph, 2, values.get("job_title") or "")
        elif full.startswith("MSNV"):
            _set_text_node(paragraph, 2, values.get("emp_code") or "")
        elif full.startswith("Ca làm việc"):
            _set_text_node(paragraph, 2, values.get("work_shift") or "")
        elif full.startswith("Tình trạng sức khỏe"):
            health = (values.get("health_status") or "").rstrip(".")
            _set_text_node(paragraph, 1, f": {health}." if health else ": ")
        elif "Tp.HCM" in full and "ngày" in full:
            for node in paragraph.iter(f"{W}t"):
                text = node.text or ""
                if text == "…..":
                    if not day_dots_done:
                        _write_t(node, values.get("sign_day") or "")
                        day_dots_done = True
                    else:
                        _write_t(node, values.get("sign_month") or "")
                elif text == "………":
                    _write_t(node, values.get("sign_year") or "")

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def _paragraph_text(paragraph):
    return "".join(node.text or "" for node in paragraph.iter(f"{W}t"))


def _text_nodes(paragraph):
    return list(paragraph.iter(f"{W}t"))


def _set_text_node(paragraph, index, value):
    nodes = _text_nodes(paragraph)
    if index >= len(nodes):
        return
    _write_t(nodes[index], value)


def _write_t(node, value):
    value = value if value is not None else ""
    node.text = value
    if value[:1].isspace() or value[-1:].isspace() or "\t" in value:
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _set_gender_male_paragraph(paragraph, selected):
    nodes = _text_nodes(paragraph)
    # Template parts: [' X  ', ' ', ' ', 'Nam            ']
    if len(nodes) < 4:
        return
    if selected:
        _write_t(nodes[0], " X  ")
    else:
        _write_t(nodes[0], "    ")
    _write_t(nodes[1], " ")
    _write_t(nodes[2], " ")
    _write_t(nodes[3], "Nam            ")


def _set_gender_female_paragraph(paragraph, selected):
    nodes = _text_nodes(paragraph)
    # Template parts: ['     ', 'Nữ']
    if len(nodes) < 2:
        return
    if selected:
        _write_t(nodes[0], " X   ")
    else:
        _write_t(nodes[0], "     ")
    _write_t(nodes[1], "Nữ")


def _employee_portrait_jpeg(employee):
    """Replace the sample portrait when the employee has an image."""
    if Image is None or not employee:
        return None
    raw = employee.with_context(bin_size=False).image_1920
    if not raw:
        return None
    try:
        import base64

        image_bytes = base64.b64decode(raw)
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        elif image.mode == "L":
            image = image.convert("RGB")
        image = _fit_cover(image, PORTRAIT_SIZE)
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return None


def _fit_cover(image, size):
    target_w, target_h = size
    src_w, src_h = image.size
    scale = max(target_w / float(src_w), target_h / float(src_h))
    resized = image.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))), Image.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))
