# -*- coding: utf-8 -*-

import logging
import re
from datetime import date

from .id_card_qr import _fit_long_side, _load_rgb, _unwrap_image_bytes

_logger = logging.getLogger(__name__)

_LABEL_NAME = re.compile(r"(họ\s*và\s*tên|ho\s*va\s*ten|full\s*name)", re.IGNORECASE)
_LABEL_BIRTH = re.compile(r"(ngày\s*sinh|ngay\s*sinh|date\s*of\s*birth)", re.IGNORECASE)
_LABEL_SEX = re.compile(
    r"(?:giới\s*tính|gioi\s*tinh|sex)\s*:?\s*(nam|nữ|nu)\b",
    re.IGNORECASE,
)
_LABEL_ORIGIN = re.compile(
    r"(quê\s*quán|que\s*quan|place\s*of\s*origin)",
    re.IGNORECASE,
)
_LABEL_RESIDENCE = re.compile(
    r"(nơi\s*thường\s*trú|noi\s*thuong\s*tru|place\s*of\s*residence|residenc\w*)",
    re.IGNORECASE,
)
_ADDRESS_HINT = re.compile(
    r"(phường|phuong|quận|quan|thành|thanh|tỉnh|tinh|tp\.|huyện|huyen|xã|xa|đường|duong|,)",
    re.IGNORECASE,
)
_ID_NUMBER = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_ISSUING_AUTHORITY = "Cục Cảnh Sát"


def parse_cccd_text(text):
    """Map printed CCCD front text to hr.employee values.

    The result is empty unless both a 12-digit ID and a birth date are present.
    Issue date is not read from the printed card. Place of origin is included
    when its label is found.
    """
    lines = _text_lines(text)
    blob = "\n".join(lines)
    identification_id = _identification_id(blob)
    birthday = _birthday(lines, blob)
    if not identification_id or not birthday:
        return {}
    values = {
        "identification_id": identification_id,
        "birthday": birthday,
    }
    name = _name(lines)
    if name:
        values["name"] = name
    gender = _gender(lines)
    if gender:
        values["gender"] = gender
    address = _residence(lines)
    if address:
        values["emp_permanent_address"] = address
    origin = _place_of_origin(lines)
    if origin:
        values["emp_place_of_origin"] = origin
    return _apply_card_defaults(values)


def merge_card_reads(qr_values, ocr_text):
    """Prefer QR fields. Place of origin always comes from the printed text.

    When the QR payload is empty, every field comes from OCR.
    """
    if qr_values:
        values = dict(qr_values)
        origin = _place_of_origin(_text_lines(ocr_text))
        if origin:
            values["emp_place_of_origin"] = origin
        return _apply_card_defaults(values)
    return parse_cccd_text(ocr_text)


def _apply_card_defaults(values):
    """Temporary address matches the permanent address. Issue place is fixed."""
    if not values:
        return values
    address = values.get("emp_permanent_address")
    if address:
        values["emp_temporary_address"] = address
    values["identification_by"] = _ISSUING_AUTHORITY
    return values


def decode_id_card_front(raw):
    """Read one CCCD photo and return employee field values, or {}."""
    values, _status = inspect_id_card(raw)
    return values


def decode_id_card(front=None, back=None, prefer="front"):
    values, _status = inspect_id_card(front, back, prefer=prefer)
    return values


def inspect_id_card_front(raw):
    """Read a single CCCD photo (kept for callers that only have one image)."""
    return inspect_id_card(raw)


def inspect_id_card(front=None, back=None, prefer="front"):
    """Read QR from either side, then OCR.

    QR is tried on the preferred side first, then the other side. A decoded
    QR fills the card fields. OCR of the front (or the only photo) adds
    place of origin, or fills every field when no QR is found.
    """
    if not front and not back:
        return {}, "empty"
    from .id_card_qr import decode_id_card_front as decode_qr

    sides = (("front", front), ("back", back))
    if prefer == "back":
        sides = (("back", back), ("front", front))
    qr_values = {}
    qr_side = None
    for side, raw in sides:
        if not raw:
            continue
        values = decode_qr(raw) or {}
        if values:
            qr_values = values
            qr_side = side
            break
    ocr_raw = front or back
    text, status = _read_text(ocr_raw) if ocr_raw else ("", "empty")
    if qr_values:
        _logger.info(
            "CCCD QR decoded from %s; OCR is used for place of origin only.",
            qr_side,
        )
        return merge_card_reads(qr_values, text if status == "ok" else ""), "ok"
    if status != "ok":
        _logger.warning("CCCD was not read: %s", status)
        return {}, status.split()[0]
    values = parse_cccd_text(text)
    if not values:
        _logger.warning("CCCD OCR found text but not a 12-digit ID and birth date.")
        return {}, "not_found"
    return values, "ok"


def _read_text(raw):
    data = _unwrap_image_bytes(raw)
    if not data:
        return "", "unreadable"
    image = _load_rgb(data)
    if image is None:
        return "", "unreadable"
    image = _fit_long_side(image, 2000)
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        _logger.warning("pytesseract is not installed; CCCD text cannot be read.")
        return "", "unreadable"
    try:
        text = pytesseract.image_to_string(
            Image.fromarray(image),
            lang="vie+eng",
            config="--psm 4",
        )
    except Exception:
        _logger.warning("Tesseract could not read the CCCD front.", exc_info=True)
        return "", "unreadable"
    if not (text or "").strip():
        height, width = image.shape[:2]
        return "", "not_found %sx%s" % (width, height)
    return text, "ok"


def _text_lines(text):
    lines = [_clean_line(line) for line in (text or "").splitlines()]
    return [line for line in lines if line]


def _clean_line(line):
    return re.sub(r"\s+", " ", (line or "").strip())


def _identification_id(blob):
    match = _ID_NUMBER.search(blob or "")
    return match.group(1) if match else ""


def _birthday(lines, blob):
    for line in lines:
        if _LABEL_BIRTH.search(line):
            found = _find_date(line)
            if found:
                return found
    return _find_date(blob)


def _find_date(text):
    compact = re.sub(r"(?<=\d)\s+(?=\d)", "", text or "")
    match = _DATE.search(compact)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    if year < 1900 or year > date.today().year:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _name(lines):
    for index, line in enumerate(lines):
        if not _LABEL_NAME.search(line):
            continue
        tail = _LABEL_NAME.sub(" ", line)
        tail = re.sub(r"(?i)\bfull\s*name\b", " ", tail)
        cleaned = _clean_name(tail)
        if len(cleaned.split()) >= 2:
            return cleaned
        if index + 1 < len(lines):
            cleaned = _clean_name(lines[index + 1])
            if len(cleaned.split()) >= 2:
                return cleaned
    return ""


def _clean_name(line):
    words = []
    for word in re.sub(r"[^\w\s]", " ", line or "", flags=re.UNICODE).split():
        letters = "".join(_LETTER.findall(word))
        if len(letters) >= 2:
            words.append(letters)
    return " ".join(words)


def _gender(lines):
    for line in lines:
        match = _LABEL_SEX.search(line)
        if not match:
            continue
        value = match.group(1).casefold()
        if value in {"nữ", "nu"}:
            return "female"
        if value == "nam":
            return "male"
    return ""


def _place_of_origin(lines):
    for index, line in enumerate(lines):
        if not _LABEL_ORIGIN.search(line):
            continue
        tail = _LABEL_ORIGIN.sub(" ", line)
        tail = re.sub(r"(?i)\bplace\s*of\s*origin\b", " ", tail)
        tail = re.sub(r"^[\s:/\-]+", "", tail)
        parts = []
        if _address_piece(tail):
            parts.append(tail)
        for follower in lines[index + 1:]:
            if _stops_origin(follower):
                break
            if _address_piece(follower):
                parts.append(follower)
                continue
            if parts:
                break
        text = " ".join(part.strip(" .-") for part in parts if part.strip(" .-"))
        return re.sub(r"\s+", " ", text).strip(" .,")
    return ""


def _stops_origin(line):
    return bool(
        _LABEL_NAME.search(line)
        or _LABEL_BIRTH.search(line)
        or _LABEL_SEX.search(line)
        or _LABEL_RESIDENCE.search(line)
        or re.search(r"(quốc\s*tịch|quoc\s*tich|nationality)", line, re.IGNORECASE)
    )


def _residence(lines):
    start = None
    for index, line in enumerate(lines):
        if _LABEL_RESIDENCE.search(line):
            start = index
            break
    if start is None:
        return ""
    tail = _LABEL_RESIDENCE.split(lines[start], maxsplit=1)[-1]
    tail = re.sub(r"^[\s:.\-]+", "", tail)
    parts = []
    if _address_piece(tail):
        parts.append(tail)
    for line in lines[start + 1:]:
        if _LABEL_NAME.search(line) or _LABEL_BIRTH.search(line) or _LABEL_SEX.search(line):
            break
        if _address_piece(line):
            parts.append(line)
            continue
        if parts:
            break
    text = " ".join(part.strip(" .-") for part in parts if part.strip(" .-"))
    return re.sub(r"\s+", " ", text).strip(" .,")


def _address_piece(line):
    text = (line or "").strip(" .-")
    if len(text) < 3:
        return False
    return bool(_ADDRESS_HINT.search(text) or re.search(r"\d", text))
