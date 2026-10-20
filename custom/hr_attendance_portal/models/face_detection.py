# -*- coding: utf-8 -*-

import base64
import logging
import os
import threading

_logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 0.7
MIN_FACE_WIDTH_RATIO = 0.12
MIN_FACE_PIXELS = 24
DETECT_MAX_SIDE = 512
YUNET_MODEL = "face_detection_yunet_2023mar.onnx"

_lock = threading.Lock()
_yunet_detector = None
_yunet_failed = False
_haar_cascade = None
_haar_failed = False
_cv_threads_ready = False


def configure_cv_threads():
    """Keep YuNet/SFace on one CPU thread so prefork workers do not oversubscribe."""
    global _cv_threads_ready
    if _cv_threads_ready:
        return
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "OPENCV_FOR_THREADS_NUM",
    ):
        os.environ.setdefault(key, "1")
    try:
        import cv2

        cv2.setNumThreads(1)
        if hasattr(cv2, "ocl") and hasattr(cv2.ocl, "setUseOpenCL"):
            cv2.ocl.setUseOpenCL(False)
    except Exception:
        pass
    _cv_threads_ready = True


def _image_for_detect(image):
    """Downscale so YuNet/SFace run on at most DETECT_MAX_SIDE pixels on the long edge."""
    import cv2

    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= DETECT_MAX_SIDE:
        return image
    scale = DETECT_MAX_SIDE / float(longest)
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def yunet_model_path():
    return os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "data", YUNET_MODEL,
    ))


def detect_face_count(image_bytes):
    """Return (count, reason).

    reason is False when at least one face is present, 'no_face' when the image
    decoded but no face was large enough, or 'face_check_unavailable' when the
    detector cannot run.
    """
    try:
        import cv2  # noqa: F401
        import numpy as np  # noqa: F401
    except ImportError:
        _logger.warning(
            "opencv-python-headless is not installed; punch photos cannot be checked for a face."
        )
        return 0, "face_check_unavailable"

    image = _decode_image(image_bytes)
    if image is None:
        return 0, "no_face"
    image = _image_for_detect(image)
    height, width = image.shape[:2]
    if width < MIN_FACE_PIXELS or height < MIN_FACE_PIXELS:
        return 0, "no_face"

    count = _detect_with_yunet(image)
    if count is None:
        count = _detect_with_haar(image)
    if count is None:
        return 0, "face_check_unavailable"
    if count < 1:
        return 0, "no_face"
    return count, False


_IMAGE_MAGIC = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG",       # PNG
    b"RIFF",          # WebP
    b"GIF8",          # GIF
    b"BM",            # BMP
)


def unwrap_image_bytes(image_bytes):
    """Return raw image bytes, decoding Odoo Binary/base64 cache values if needed."""
    if not image_bytes:
        return b""
    if isinstance(image_bytes, memoryview):
        image_bytes = image_bytes.tobytes()
    elif isinstance(image_bytes, str):
        raw = image_bytes.strip()
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        try:
            return base64.b64decode(raw)
        except (TypeError, ValueError):
            return raw.encode("utf-8", errors="ignore")
    data = bytes(image_bytes)
    stripped = data.lstrip()
    if stripped.startswith(b"data:"):
        stripped = stripped.split(b",", 1)[-1]
        try:
            return base64.b64decode(stripped)
        except (TypeError, ValueError):
            return data
    if stripped.startswith(_IMAGE_MAGIC):
        return stripped
    try:
        decoded = base64.b64decode(stripped, validate=False)
    except (TypeError, ValueError):
        return data
    if decoded.startswith(_IMAGE_MAGIC) or (decoded and not stripped.startswith(_IMAGE_MAGIC)):
        return decoded
    return data


def _decode_image(image_bytes):
    import cv2
    import numpy as np

    configure_cv_threads()
    data = unwrap_image_bytes(image_bytes)
    if not data:
        return None
    array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is not None and image.size:
        return image
    try:
        from io import BytesIO
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        pil = Image.open(BytesIO(data))
        pil = ImageOps.exif_transpose(pil)
        if pil.mode != "RGB":
            pil = pil.convert("RGB")
        rgb = np.asarray(pil)
        if rgb.size == 0:
            return None
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        _logger.exception("Could not decode enroll/punch image with Pillow.")
        return None


def _min_face_width(image):
    height, width = image.shape[:2]
    return max(MIN_FACE_PIXELS, int(width * MIN_FACE_WIDTH_RATIO))


def _detect_with_yunet(image):
    detector = _get_yunet_detector()
    if detector is None:
        return None
    try:
        import numpy as np

        height, width = image.shape[:2]
        with _lock:
            detector.setInputSize((width, height))
            _retval, faces = detector.detect(image)
    except Exception:
        _logger.exception("YuNet face detection failed.")
        return None
    if faces is None or len(faces) == 0:
        return 0
    min_width = _min_face_width(image)
    count = 0
    for face in np.atleast_2d(faces):
        face_width = float(face[2])
        score = float(face[-1])
        if face_width >= min_width and score >= SCORE_THRESHOLD:
            count += 1
    return count


def _get_yunet_detector():
    global _yunet_detector, _yunet_failed
    if _yunet_failed:
        return None
    if _yunet_detector is not None:
        return _yunet_detector
    with _lock:
        if _yunet_failed:
            return None
        if _yunet_detector is not None:
            return _yunet_detector
        try:
            import cv2

            configure_cv_threads()
            path = yunet_model_path()
            if not os.path.isfile(path):
                _logger.warning("YuNet model is missing at %s.", path)
                _yunet_failed = True
                return None
            if not hasattr(cv2, "FaceDetectorYN"):
                _logger.warning("This OpenCV build has no FaceDetectorYN.")
                _yunet_failed = True
                return None
            _yunet_detector = cv2.FaceDetectorYN.create(
                path,
                "",
                (320, 320),
                SCORE_THRESHOLD,
                0.3,
                5000,
            )
            return _yunet_detector
        except Exception:
            _logger.exception("Could not load YuNet face detector.")
            _yunet_failed = True
            return None


def _detect_with_haar(image):
    cascade = _get_haar_cascade()
    if cascade is None:
        return None
    try:
        import cv2

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        min_width = _min_face_width(image)
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(min_width, min_width),
        )
    except Exception:
        _logger.exception("Haar face detection failed.")
        return None
    return 0 if faces is None else len(faces)


def _get_haar_cascade():
    global _haar_cascade, _haar_failed
    if _haar_failed:
        return None
    if _haar_cascade is not None:
        return _haar_cascade
    with _lock:
        if _haar_failed:
            return None
        if _haar_cascade is not None:
            return _haar_cascade
        try:
            import cv2

            configure_cv_threads()
            path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            cascade = cv2.CascadeClassifier(path)
            if cascade.empty():
                _haar_failed = True
                return None
            _haar_cascade = cascade
            return _haar_cascade
        except Exception:
            _logger.exception("Could not load Haar face cascade.")
            _haar_failed = True
            return None
