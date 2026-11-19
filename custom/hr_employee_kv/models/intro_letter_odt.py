# -*- coding: utf-8 -*-

"""Fill the LibreOffice ODT template in-place (content.xml), then export via soffice."""

import base64
import io
import logging
import shutil
import subprocess
import tempfile
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

_logger = logging.getLogger(__name__)

TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
FO = "{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
PORTRAIT_SIZE = (244, 326)
# Filled body text: slightly smaller than template 12pt; values never bold.
BODY_FONT_SIZE = "11pt"
STYLE_LABEL = "KV_IntroLabel"
STYLE_VALUE = "KV_IntroValue"
STYLE_SIGN = "KV_IntroSign"


def build_intro_letter_odt(wizard):
    values = wizard._letter_values()
    template_key = intro_letter_template_key(wizard.employee_id.company_id)
    config = template_config(template_key)
    template_path = config["odt"]
    if not template_path.is_file():
        raise UserError(
            wizard.env._("Thiếu file mẫu ODT giấy giới thiệu nhân sự trên hệ thống.")
        )

    portrait = _employee_portrait_bytes(
        wizard.employee_id, fmt=config["portrait_format"]
    ) or _blank_portrait_bytes(fmt=config["portrait_format"])
    portrait_name = config["odt_portrait"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(template_path, "r") as src, zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "content.xml":
                data = _fill_content_xml(data, values, template_key=template_key)
            elif info.filename == portrait_name and portrait:
                data = portrait
            if info.filename.endswith((".png", ".jpeg", ".jpg")):
                dst.writestr(info, data, compress_type=zipfile.ZIP_STORED)
            else:
                dst.writestr(info.filename, data)
    return buffer.getvalue()


def export_intro_letter_pdf_from_odt(wizard):
    """Fill ODT, convert with LibreOffice, keep page 1 (LO may emit empty page 2)."""
    odt_bytes = build_intro_letter_odt(wizard)
    pdf_bytes = _soffice_convert_to_pdf(wizard, odt_bytes)
    return _first_pdf_page(pdf_bytes)


def _soffice_convert_to_pdf(wizard, odt_bytes):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise UserError(
            wizard.env._(
                "Không tìm thấy LibreOffice (soffice) để xuất PDF. "
                "Cài libreoffice-writer-nogui trên server."
            )
        )
    with tempfile.TemporaryDirectory(prefix="kv_intro_odt_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "letter.odt"
        src.write_bytes(odt_bytes)
        profile = tmp_path / "lo_profile"
        profile.mkdir()
        cmd = [
            soffice,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--norestore",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(tmp_path),
            str(src),
        ]
        try:
            completed = subprocess.run(
                cmd, check=False, capture_output=True, text=True, timeout=120
            )
        except subprocess.TimeoutExpired as exc:
            raise UserError(
                wizard.env._("Xuất PDF quá thời gian. Thử lại sau.")
            ) from exc
        out = tmp_path / "letter.pdf"
        if not out.is_file():
            candidates = sorted(tmp_path.glob("*.pdf"))
            out = candidates[0] if candidates else out
        if completed.returncode != 0 or not out.is_file():
            _logger.error(
                "LibreOffice PDF convert failed code=%s stdout=%s stderr=%s",
                completed.returncode,
                completed.stdout,
                completed.stderr,
            )
            raise UserError(
                wizard.env._("Không xuất được PDF từ mẫu LibreOffice.")
            )
        return out.read_bytes()


def _first_pdf_page(pdf_bytes):
    """Drop trailing empty pages that LibreOffice sometimes appends."""
    try:
        from pdfrw import PdfReader, PdfWriter
    except ImportError:
        return pdf_bytes
    reader = PdfReader(fdata=pdf_bytes)
    if len(reader.pages) <= 1:
        return pdf_bytes
    writer = PdfWriter()
    writer.addpage(reader.pages[0])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _fill_content_xml(xml_bytes, values, template_key=KIEN_VIET):
    root = etree.fromstring(xml_bytes)
    _ensure_fill_styles(root)
    _shrink_body_font_sizes(root)
    male = values.get("gender") == "male"
    female = values.get("gender") == "female"

    extra_recipient_lines = []
    extra_recipient_index = 0
    lines = recipient_lines(values.get("recipient"))

    for paragraph in root.iter(f"{TEXT}p"):
        full = "".join(paragraph.itertext())
        if not full.strip():
            continue

        if full.startswith("Kính gửi / To"):
            _set_labeled_field(
                paragraph,
                "Kính gửi / To",
                lines[0] if lines else "",
            )
            extra_recipient_lines = lines[1:]
            extra_recipient_index = 0
        elif template_key == THANH_NIEN and _is_thanh_nien_recipient_continuation(full):
            if extra_recipient_index < len(extra_recipient_lines):
                _set_value_only(
                    paragraph, extra_recipient_lines[extra_recipient_index]
                )
            else:
                _set_value_only(paragraph, "")
            extra_recipient_index += 1
        elif full.startswith("Kính gửi"):
            _set_labeled_field(paragraph, "Kính gửi", values.get("recipient") or "")
        elif full.startswith("Họ và tên"):
            _set_labeled_field(paragraph, "Họ và tên", values.get("name") or "")
        elif full.strip().startswith("X") and "Nam" in full and "Nữ" not in full:
            _set_value_only(paragraph, "X Nam " if male else "  Nam ")
        elif full.strip() == "Nữ" or (full.strip().endswith("Nữ") and "Nam" not in full):
            _set_value_only(paragraph, "X Nữ" if female else "Nữ")
        elif full.startswith("Ngày sinh"):
            _set_labeled_field(paragraph, "Ngày sinh", values.get("birthday") or "")
        elif full.startswith("Nơi sinh"):
            _set_labeled_field(paragraph, "Nơi sinh", values.get("place_of_origin") or "")
        elif full.startswith("CCCD"):
            _set_labeled_field(
                paragraph, "CCCD số", values.get("identification_id") or ""
            )
        elif full.startswith("Ngày cấp"):
            _set_labeled_field(
                paragraph, "Ngày cấp", values.get("identification_date") or ""
            )
        elif full.startswith("Nơi cấp"):
            _set_labeled_field(
                paragraph, "Nơi cấp", values.get("identification_by") or ""
            )
        elif full.startswith("Trình độ"):
            _set_labeled_field(
                paragraph, "Trình độ học vấn", values.get("education_level") or ""
            )
        elif full.startswith("Địa chỉ thường trú"):
            _set_labeled_field(
                paragraph, "Địa chỉ thường trú", values.get("permanent_address") or ""
            )
        elif full.startswith("Địa chỉ tạm trú"):
            _set_labeled_field(
                paragraph, "Địa chỉ tạm trú", values.get("temporary_address") or ""
            )
        elif full.startswith("Điện thoại"):
            _set_labeled_field(
                paragraph, "Điện thoại liên lạc", values.get("phone") or ""
            )
        elif full.startswith("Ngày bắt đầu"):
            _set_labeled_field(
                paragraph, "Ngày bắt đầu làm việc", values.get("date_import") or ""
            )
        elif full.startswith("Vị trí"):
            _set_labeled_field(paragraph, "Vị trí", values.get("job_title") or "")
        elif full.startswith("MSNV"):
            _set_labeled_field(paragraph, "MSNV", values.get("emp_code") or "")
        elif full.startswith("Ca làm"):
            _set_labeled_field(paragraph, "Ca làm việc", values.get("work_shift") or "")
        elif template_key == KIEN_VIET and full.startswith("Tình trạng sức khỏe"):
            health = (values.get("health_status") or "").rstrip(".")
            value = f"{health}." if health else ""
            _set_labeled_field(paragraph, "Tình trạng sức khỏe", value)
        elif "Tp.HCM" in full and "ngày" in full:
            if template_key == THANH_NIEN:
                _set_sign_line(
                    paragraph,
                    values.get("sign_day") or "",
                    values.get("sign_month") or "",
                    values.get("sign_year") or "",
                )
            else:
                _set_sign_line(
                    paragraph,
                    values.get("sign_day") or "…..",
                    values.get("sign_month") or "…..",
                    values.get("sign_year") or "………",
                )

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _ensure_fill_styles(root):
    """Label = bold 11pt; value/sign = regular 11pt Times New Roman."""
    auto = root.find(f"{OFFICE}automatic-styles")
    if auto is None:
        auto = etree.Element(f"{OFFICE}automatic-styles")
        root.insert(0, auto)

    existing = {
        st.get(f"{STYLE}name")
        for st in auto.findall(f"{STYLE}style")
        if st.get(f"{STYLE}family") == "text"
    }

    def add_text_style(name, *, bold=False, italic=False):
        if name in existing:
            return
        st = etree.SubElement(auto, f"{STYLE}style")
        st.set(f"{STYLE}name", name)
        st.set(f"{STYLE}family", "text")
        props = etree.SubElement(st, f"{STYLE}text-properties")
        props.set(f"{STYLE}font-name", "Times New Roman")
        props.set(f"{STYLE}font-name-asian", "Times New Roman")
        props.set(f"{STYLE}font-name-complex", "Times New Roman")
        props.set(f"{FO}font-size", BODY_FONT_SIZE)
        props.set(f"{STYLE}font-size-asian", BODY_FONT_SIZE)
        props.set(f"{STYLE}font-size-complex", BODY_FONT_SIZE)
        weight = "bold" if bold else "normal"
        props.set(f"{FO}font-weight", weight)
        props.set(f"{STYLE}font-weight-asian", weight)
        props.set(f"{STYLE}font-weight-complex", weight)
        if italic:
            props.set(f"{FO}font-style", "italic")
            props.set(f"{STYLE}font-style-asian", "italic")
            props.set(f"{STYLE}font-style-complex", "italic")
        existing.add(name)

    add_text_style(STYLE_LABEL, bold=True)
    add_text_style(STYLE_VALUE, bold=False)
    add_text_style(STYLE_SIGN, bold=False, italic=True)


def _shrink_body_font_sizes(root):
    """Bump template body 12pt → 11pt so filled page matches paper sample better."""
    for props in root.iter(f"{STYLE}text-properties"):
        for attr in list(props.attrib):
            if not attr.endswith("font-size"):
                continue
            if props.get(attr) == "12pt":
                props.set(attr, BODY_FONT_SIZE)


def _clear_paragraph_content(paragraph):
    paragraph.text = None
    for child in list(paragraph):
        paragraph.remove(child)


def _set_labeled_field(paragraph, label, value):
    """Bold label + regular value (never inherit template bold on data)."""
    _clear_paragraph_content(paragraph)
    label_span = etree.SubElement(paragraph, f"{TEXT}span")
    label_span.set(f"{TEXT}style-name", STYLE_LABEL)
    label_span.text = label
    value_span = etree.SubElement(paragraph, f"{TEXT}span")
    value_span.set(f"{TEXT}style-name", STYLE_VALUE)
    value_span.text = f": {value}" if value else ": "


def _set_value_only(paragraph, text):
    _clear_paragraph_content(paragraph)
    span = etree.SubElement(paragraph, f"{TEXT}span")
    span.set(f"{TEXT}style-name", STYLE_VALUE)
    span.text = text


def _set_sign_line(paragraph, day, month, year):
    _clear_paragraph_content(paragraph)
    span = etree.SubElement(paragraph, f"{TEXT}span")
    span.set(f"{TEXT}style-name", STYLE_SIGN)
    span.text = f"Tp.HCM, ngày {day} tháng {month} năm {year}"


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
    if Image is None or not employee:
        return None
    raw = employee.with_context(bin_size=False).image_1920
    if not raw:
        return None
    try:
        image = Image.open(io.BytesIO(base64.b64decode(raw)))
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
        _logger.exception("Could not prepare employee portrait for ODT letter.")
        return None


def _fit_cover(image, size):
    target_w, target_h = size
    src_w, src_h = image.size
    scale = max(target_w / float(src_w), target_h / float(src_h))
    resized = image.resize(
        (max(1, int(src_w * scale)), max(1, int(src_h * scale))), Image.LANCZOS
    )
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))
