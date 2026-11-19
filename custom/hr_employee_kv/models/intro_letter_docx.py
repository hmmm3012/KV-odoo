# -*- coding: utf-8 -*-

"""Fill the official Word template by editing XML in-place.

python-docx rewrite destroys headers/drawings/styles. Instead we copy the
template ZIP and only change <w:t> text nodes (and optionally the portrait).
"""

import copy
import io
import zipfile
from pathlib import Path

from lxml import etree
from odoo.exceptions import UserError

from .intro_letter_templates import (
    KIEN_VIET,
    THANH_NIEN,
    intro_letter_template_key,
    recipient_lines,
    template_config,
)

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
IMAGE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
)
THANH_NIEN_PORTRAIT_RID = "rIdKvEmpPortrait"
THANH_NIEN_PORTRAIT_ZIP = "word/media/portrait.jpeg"
PORTRAIT_SIZE = (244, 326)
_PORTRAIT_INLINE_REFERENCE = None


def build_intro_letter_docx(wizard):
    values = wizard._letter_values()
    template_key = intro_letter_template_key(wizard.employee_id.company_id)
    config = template_config(template_key)
    template_path = config["docx"]
    if not template_path.is_file():
        raise UserError(
            wizard.env._("Thiếu file mẫu giấy giới thiệu nhân sự trên hệ thống.")
        )

    portrait_bytes = _employee_portrait_bytes(
        wizard.employee_id, fmt=config["portrait_format"]
    ) or _blank_portrait_bytes(fmt=config["portrait_format"])
    portrait_name = config.get("docx_portrait")
    use_vml = config.get("docx_portrait_vml")
    buffer = io.BytesIO()
    with zipfile.ZipFile(template_path, "r") as src:
        archive = {info.filename: src.read(info.filename) for info in src.infolist()}

    archive["word/document.xml"] = _fill_document_xml(
        archive["word/document.xml"], values, template_key=template_key
    )
    if use_vml and portrait_bytes:
        rels_name = "word/_rels/document.xml.rels"
        if rels_name in archive:
            archive["word/document.xml"], archive[rels_name] = _inject_thanh_nien_portrait(
                archive["word/document.xml"],
                archive[rels_name],
            )
        archive[THANH_NIEN_PORTRAIT_ZIP] = portrait_bytes
        _ensure_jpeg_content_type(archive)
    elif portrait_name and portrait_bytes and portrait_name in archive:
        archive[portrait_name] = portrait_bytes

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for filename, data in archive.items():
            if filename.endswith((".png", ".jpeg", ".jpg")):
                dst.writestr(filename, data, compress_type=zipfile.ZIP_STORED)
            else:
                dst.writestr(filename, data)
    return buffer.getvalue()


def _fill_document_xml(xml_bytes, values, template_key=KIEN_VIET):
    root = etree.fromstring(xml_bytes)
    male = values.get("gender") == "male"
    female = values.get("gender") == "female"

    day_dots_done = False
    extra_recipient_lines = []
    extra_recipient_index = 0
    lines = recipient_lines(values.get("recipient"))

    for paragraph in root.iter(f"{W}p"):
        full = _paragraph_text(paragraph)
        if not full:
            continue

        if full.startswith("Kính gửi / To"):
            _set_field_value(
                paragraph,
                "Kính gửi / To",
                lines[0] if lines else "",
            )
            extra_recipient_lines = lines[1:]
            extra_recipient_index = 0
        elif template_key == THANH_NIEN and _is_thanh_nien_recipient_continuation(full):
            if extra_recipient_index < len(extra_recipient_lines):
                _set_paragraph_text(
                    paragraph, extra_recipient_lines[extra_recipient_index]
                )
            else:
                _set_paragraph_text(paragraph, "")
            extra_recipient_index += 1
        elif full.startswith("Kính gửi"):
            _set_field_value(paragraph, "Kính gửi", values.get("recipient") or "")
        elif full.startswith("Họ và tên"):
            _set_field_value(paragraph, "Họ và tên", values.get("name") or "")
        elif "Nam" in full and "Nữ" not in full:
            _set_gender_male_paragraph(paragraph, selected=male)
        elif "Nữ" in full and "Nam" not in full:
            _set_gender_female_paragraph(paragraph, selected=female)
        elif full.startswith("Ngày sinh"):
            _set_field_value(paragraph, "Ngày sinh", values.get("birthday") or "")
        elif full.startswith("Nơi sinh"):
            _set_field_value(paragraph, "Nơi sinh", values.get("place_of_origin") or "")
        elif full.startswith("CCCD số"):
            _set_field_value(paragraph, "CCCD số", values.get("identification_id") or "")
        elif full.startswith("Ngày cấp"):
            _set_field_value(paragraph, "Ngày cấp", values.get("identification_date") or "")
        elif full.startswith("Nơi cấp"):
            _set_field_value(paragraph, "Nơi cấp", values.get("identification_by") or "")
        elif full.startswith("Trình độ học vấn"):
            _set_field_value(
                paragraph, "Trình độ học vấn", values.get("education_level") or ""
            )
        elif full.startswith("Địa chỉ thường trú"):
            _set_field_value(
                paragraph, "Địa chỉ thường trú", values.get("permanent_address") or ""
            )
        elif full.startswith("Địa chỉ tạm trú"):
            _set_field_value(
                paragraph, "Địa chỉ tạm trú", values.get("temporary_address") or ""
            )
        elif full.startswith("Điện thoại liên lạc"):
            _set_field_value(
                paragraph, "Điện thoại liên lạc", values.get("phone") or ""
            )
        elif full.startswith("Ngày bắt đầu làm việc"):
            _set_field_value(
                paragraph, "Ngày bắt đầu làm việc", values.get("date_import") or ""
            )
        elif full.startswith("Vị trí"):
            _set_field_value(paragraph, "Vị trí", values.get("job_title") or "")
        elif full.startswith("MSNV"):
            _set_field_value(paragraph, "MSNV", values.get("emp_code") or "")
        elif full.startswith("Ca làm việc"):
            _set_field_value(paragraph, "Ca làm việc", values.get("work_shift") or "")
        elif template_key == KIEN_VIET and full.startswith("Tình trạng sức khỏe"):
            health = (values.get("health_status") or "").rstrip(".")
            _set_field_value(
                paragraph, "Tình trạng sức khỏe", f"{health}." if health else ""
            )
        elif template_key == THANH_NIEN and "Tp.HCM" in full and "ngày" in full:
            sign = (
                f"     Tp.HCM, ngày {values.get('sign_day') or ''} "
                f"tháng {values.get('sign_month') or ''} "
                f"năm {values.get('sign_year') or ''}"
            )
            _set_paragraph_text(paragraph, sign)
        elif template_key == KIEN_VIET and "Tp.HCM" in full and "ngày" in full:
            for node in paragraph.iter(f"{W}t"):
                text = node.text or ""
                if text == "…..":
                    if not day_dots_done:
                        _write_t(node, values.get("sign_day") or "")
                        day_dots_done = True
                    else:
                        # Template run is " tháng" with no space before the dots.
                        _write_t(node, f" {values.get('sign_month') or ''}")
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


def _set_field_value(paragraph, label, value):
    """Write ``label: value`` without depending on how Word split the runs.

    The official template keeps the sample person (Dương Tuấn Anh) in the value
    run. Some rows are ``[label, ': value']``, some ``[label, ': ', value]``,
    and some a single run ``'label: value'``. Index-based writes miss the short
    rows and leave the sample birthday, start date, employee code, and shift.
    """
    nodes = _text_nodes(paragraph)
    if not nodes:
        return
    texts = [node.text or "" for node in nodes]
    full = "".join(texts)
    start = full.find(label)
    if start < 0:
        return
    label_end = start + len(label)
    new_value = f": {value}" if value else ": "
    consumed = 0
    value_written = False
    for node, text in zip(nodes, texts):
        node_start = consumed
        node_end = consumed + len(text)
        consumed = node_end
        if node_end <= label_end:
            continue
        if node_start >= label_end:
            if not value_written:
                _write_t(node, new_value)
                value_written = True
            else:
                _write_t(node, "")
            continue
        keep = text[: label_end - node_start]
        _write_t(node, keep + new_value)
        value_written = True
    if not value_written:
        last = nodes[-1]
        _write_t(last, (last.text or "") + new_value)


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


def _set_paragraph_text(paragraph, text):
    nodes = _text_nodes(paragraph)
    if not nodes:
        return
    _write_t(nodes[0], text or "")
    for node in nodes[1:]:
        _write_t(node, "")


def _kien_viet_portrait_inline_reference():
    """Picture drawing from the Kiến Việt letter (Word displays it reliably)."""
    global _PORTRAIT_INLINE_REFERENCE
    if _PORTRAIT_INLINE_REFERENCE is None:
        ref_path = template_config(KIEN_VIET)["docx"]
        with zipfile.ZipFile(ref_path, "r") as src:
            doc = etree.fromstring(src.read("word/document.xml"))
        _PORTRAIT_INLINE_REFERENCE = next(doc.iter(WP + "inline"))
    return copy.deepcopy(_PORTRAIT_INLINE_REFERENCE)


def _inject_thanh_nien_portrait(document_xml, rels_xml):
    """Replace the empty text-box anchor with a real inline picture (keep header logo untouched)."""
    rels_root = etree.fromstring(rels_xml)
    existing_ids = {rel.get("Id") for rel in rels_root}
    if THANH_NIEN_PORTRAIT_RID not in existing_ids:
        rel = etree.SubElement(rels_root, REL_PKG + "Relationship")
        rel.set("Id", THANH_NIEN_PORTRAIT_RID)
        rel.set("Type", IMAGE_REL_TYPE)
        rel.set("Target", "media/portrait.jpeg")

    inline = _kien_viet_portrait_inline_reference()
    blip = inline.find(".//" + A + "blip")
    if blip is not None:
        blip.set(R + "embed", THANH_NIEN_PORTRAIT_RID)

    doc_root = etree.fromstring(document_xml)
    for anchor in doc_root.iter(WP + "anchor"):
        doc_pr = anchor.find(WP + "docPr")
        if doc_pr is None or doc_pr.get("name") != "Text Box 2":
            continue
        drawing = anchor.getparent()
        if drawing is not None:
            drawing.remove(anchor)
            drawing.append(inline)
        break

    return (
        etree.tostring(
            doc_root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        ),
        etree.tostring(
            rels_root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        ),
    )


def _ensure_jpeg_content_type(archive):
    ct_name = "[Content_Types].xml"
    if ct_name not in archive:
        return
    root = etree.fromstring(archive[ct_name])
    for default in root.findall(f"{CT_NS}Default"):
        if default.get("Extension") == "jpeg":
            return
    default = etree.SubElement(root, f"{CT_NS}Default")
    default.set("Extension", "jpeg")
    default.set("ContentType", "image/jpeg")
    archive[ct_name] = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def _is_thanh_nien_recipient_continuation(full):
    if full.startswith("Phòng nhân sự"):
        return False
    if full.startswith("BAN QUẢN"):
        return True
    if full.startswith("Anh ") or full.startswith("Chị "):
        return True
    return False


def _blank_portrait_bytes(fmt="jpeg"):
    """White photo box so the template sample portrait is never printed."""
    if Image is None:
        return None
    image = Image.new("RGB", PORTRAIT_SIZE, (255, 255, 255))
    out = io.BytesIO()
    if fmt == "png":
        image.save(out, format="PNG")
    else:
        image.save(out, format="JPEG", quality=85)
    return out.getvalue()


def _employee_portrait_bytes(employee, fmt="jpeg"):
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
        if fmt == "png":
            image.save(out, format="PNG")
        else:
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
