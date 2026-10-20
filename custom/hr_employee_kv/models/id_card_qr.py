# -*- coding: utf-8 -*-

import base64
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

_GENDER = {
    "nam": "male",
    "male": "male",
    "m": "male",
    "nữ": "female",
    "nu": "female",
    "female": "female",
    "f": "female",
}


def parse_cccd_payload(payload):
    """Map a Vietnamese chip-ID QR payload to hr.employee values.

    Expected shape:
    CCCD|old CMND|full name|ddMMyyyy|gender|permanent address|issue ddMMyyyy
    Extra trailing parts are ignored. The old CMND number is not returned.
    """
    text = (payload or "").strip().lstrip("\ufeff")
    parts = [part.strip() for part in text.split("|")]
    if len(parts) < 6:
        return {}
    cccd = parts[0]
    if not cccd.isdigit() or len(cccd) not in (9, 12):
        return {}
    birthday = _parse_date(parts[3])
    if not birthday:
        return {}
    values = {
        "identification_id": cccd,
        "birthday": birthday,
    }
    if parts[2]:
        values["name"] = parts[2]
    gender = _GENDER.get(parts[4].casefold())
    if gender:
        values["gender"] = gender
    if parts[5]:
        values["emp_permanent_address"] = parts[5]
    if len(parts) > 6 and parts[6]:
        issue_date = _parse_date(parts[6])
        if issue_date:
            values["identification_date"] = issue_date
    return values


def decode_id_card_front(raw):
    """Read the front-side QR and return employee field values, or {}."""
    values, _status = inspect_id_card_front(raw)
    return values


def inspect_id_card_front(raw):
    """Return (field values, status).

    status is ok, empty, unreadable, not_found, or not_cccd.
    """
    if not raw:
        return {}, "empty"
    payload, status = _read_qr_text(raw)
    if status != "ok":
        _logger.warning("CCCD front image: %s", status)
        return {}, status.split()[0]
    values = parse_cccd_payload(payload)
    if not values:
        _logger.warning(
            "CCCD QR text was read (%s characters, %s parts) but it is not a CCCD payload.",
            len(payload),
            payload.count("|") + 1,
        )
        return {}, "not_cccd"
    return values, "ok"


def _parse_date(value):
    text = (value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return False
    try:
        return datetime.strptime(text, "%d%m%Y").date()
    except ValueError:
        return False


def _unwrap_image_bytes(raw):
    if not raw:
        return b""
    if isinstance(raw, str):
        if raw.startswith("data:") and "," in raw[:80]:
            raw = raw.split(",", 1)[1]
        raw = raw.encode()
    if raw.startswith((b"\xff\xd8", b"\x89PNG", b"GIF8", b"RIFF")):
        return raw
    try:
        decoded = base64.b64decode(raw, validate=False)
    except Exception:
        return raw
    return decoded or raw


def _read_qr_text(raw):
    """Locate a QR code, then decode its text.

    1. Open the photo and honor camera orientation.
    2. Scale the long side to about 2000 px.
    3. Decode with ZXing on the full photo, then on a contrast-stretched copy.
    4. Crop the upper-right half, enlarge it, and decode that.
    5. Fall back to OpenCV on the full photo and the crop.
    """
    data = _unwrap_image_bytes(raw)
    if not data:
        return "", "unreadable"
    image = _load_rgb(data)
    if image is None:
        return "", "unreadable"
    image = _fit_long_side(image, 2000)
    for view_name, view in _scan_views(image):
        text = _decode_zxing(view) or _decode_opencv(view)
        if text:
            _logger.info("CCCD QR decoded from the %s view.", view_name)
            return text.strip(), "ok"
    height, width = image.shape[:2]
    return "", "not_found %sx%s" % (width, height)


def _load_rgb(data):
    import cv2
    import numpy as np

    try:
        from io import BytesIO

        from PIL import Image, ImageOps

        pil = ImageOps.exif_transpose(Image.open(BytesIO(data)))
        rgb = np.asarray(pil.convert("RGB"))
        if rgb.size:
            return np.ascontiguousarray(rgb)
    except Exception:
        _logger.debug("Pillow could not open the ID photo.", exc_info=True)
    array = np.frombuffer(data, dtype=np.uint8)
    bgr = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if bgr is None or not bgr.size:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _fit_long_side(image, long_side):
    import cv2

    height, width = image.shape[:2]
    longest = max(height, width)
    if not longest or abs(longest - long_side) < longest * 0.05:
        return image
    scale = long_side / longest
    interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    return cv2.resize(image, (max(int(width * scale), 1), max(int(height * scale), 1)), interpolation=interpolation)


def _scan_views(image):
    import cv2

    yield "full photo", image
    yield "full photo, higher contrast", _boost_contrast(image)
    height, width = image.shape[:2]
    crop = image[0:max(int(height * 0.5), 1), min(int(width * 0.5), width - 1):width]
    if not crop.size:
        return
    crop = _fit_long_side(crop, 1400)
    crop = cv2.copyMakeBorder(crop, 32, 32, 32, 32, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    yield "upper-right crop", crop
    yield "upper-right crop, higher contrast", _boost_contrast(crop)


def _boost_contrast(image):
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)


def _decode_zxing(image):
    try:
        import zxingcpp
    except ImportError:
        _logger.warning("zxing-cpp is not installed; QR decoding falls back to OpenCV.")
        return ""
    binarizers = [zxingcpp.Binarizer.LocalAverage, zxingcpp.Binarizer.GlobalHistogram]
    for binarizer in binarizers:
        try:
            results = zxingcpp.read_barcodes(
                image,
                formats=zxingcpp.BarcodeFormat.QRCode,
                try_rotate=True,
                try_downscale=True,
                binarizer=binarizer,
            )
        except Exception:
            _logger.debug("ZXing decode failed.", exc_info=True)
            return ""
        for result in results or []:
            text = (getattr(result, "text", "") or "").strip()
            if text:
                return text
    return ""


def _decode_opencv(image):
    try:
        import cv2
    except ImportError:
        return ""
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    detectors = []
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    detectors.append(cv2.QRCodeDetector())
    for detector in detectors:
        method = getattr(detector, "detectAndDecode", None)
        if not method:
            continue
        try:
            text = _first_text(method(bgr))
        except Exception:
            _logger.debug("OpenCV QR decode failed.", exc_info=True)
            continue
        if text:
            return text
    return ""


def _first_text(result):
    if isinstance(result, str):
        return result.strip()
    if not isinstance(result, tuple):
        return ""
    for part in result:
        if isinstance(part, str) and part.strip():
            return part.strip()
        if isinstance(part, (list, tuple)):
            for item in part:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return ""
