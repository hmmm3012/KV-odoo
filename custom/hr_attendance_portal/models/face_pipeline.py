# -*- coding: utf-8 -*-

import logging
import math
import os
import threading

from . import face_detection as presence

_logger = logging.getLogger(__name__)

SFACE_MODEL = "face_recognition_sface_2021dec.onnx"
ALIGN_SIZE = 112
MIN_FACE_PX = 80
MIN_FACE_RATIO = 0.20
MAX_ROLL_DEG = 15.0
MAX_YAW_RATIO = 0.35
COSINE_ACCEPT = 0.45
COSINE_REVIEW = 0.30

QUALITY_RECAPTURE = frozenset({
    "no_face",
    "multiple_faces",
    "face_too_small",
    "face_tilted",
    "face_turned",
    "face_low_match",
})

_sface_lock = threading.Lock()
_sface = None
_sface_failed = False


def sface_model_path():
    return os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "data", SFACE_MODEL,
    ))


def detect_face_count(image_bytes):
    """Backward-compatible presence check used by older call sites."""
    return presence.detect_face_count(image_bytes)


def process_face(image_bytes):
    """Detect, score quality, align, and embed.

    Returns a dict:
      unavailable, face_count, quality_reason, embedding (list[float] or None)
    """
    empty = {
        "unavailable": False,
        "face_count": 0,
        "quality_reason": "no_face",
        "embedding": None,
    }
    try:
        import cv2  # noqa: F401
        import numpy as np  # noqa: F401
    except ImportError:
        return {
            "unavailable": True,
            "face_count": 0,
            "quality_reason": "face_check_unavailable",
            "embedding": None,
        }

    image = presence._decode_image(image_bytes)
    if image is None:
        return empty
    image = presence._image_for_detect(image)

    faces = _detect_yunet_faces(image)
    if faces is None:
        return {
            "unavailable": True,
            "face_count": 0,
            "quality_reason": "face_check_unavailable",
            "embedding": None,
        }
    if not faces:
        empty["face_count"] = 0
        return empty

    scored = [face for face in faces if float(face[-1]) >= presence.SCORE_THRESHOLD]
    if not scored:
        empty["face_count"] = 0
        return empty
    if len(scored) > 1:
        return {
            "unavailable": False,
            "face_count": len(scored),
            "quality_reason": "multiple_faces",
            "embedding": None,
        }

    face = scored[0]
    quality = evaluate_quality(image, face)
    if quality:
        return {
            "unavailable": False,
            "face_count": 1,
            "quality_reason": quality,
            "embedding": None,
        }

    embedding = embed_aligned(image, face)
    if embedding is None:
        return {
            "unavailable": True,
            "face_count": 1,
            "quality_reason": "face_check_unavailable",
            "embedding": None,
        }
    return {
        "unavailable": False,
        "face_count": 1,
        "quality_reason": False,
        "embedding": embedding,
    }


def evaluate_quality(image, face):
    """Return a recapture reason or False if the face is usable."""
    import numpy as np

    height, width = image.shape[:2]
    box_w = float(face[2])
    box_h = float(face[3])
    min_side = min(height, width)
    if box_w < MIN_FACE_PX or box_w < (min_side * MIN_FACE_RATIO) or box_h < MIN_FACE_PX:
        return "face_too_small"

    right_eye = np.array([float(face[4]), float(face[5])])
    left_eye = np.array([float(face[6]), float(face[7])])
    nose = np.array([float(face[8]), float(face[9])])
    eye_vec = left_eye - right_eye
    eye_dist = float(np.linalg.norm(eye_vec))
    if eye_dist < 1:
        return "face_too_small"

    roll_deg = abs(math.degrees(math.atan2(eye_vec[1], eye_vec[0])))
    if roll_deg > 90:
        roll_deg = abs(roll_deg - 180)
    if roll_deg > MAX_ROLL_DEG:
        return "face_tilted"

    mid = (left_eye + right_eye) / 2.0
    yaw_ratio = abs(float(nose[0] - mid[0])) / eye_dist
    if yaw_ratio > MAX_YAW_RATIO:
        return "face_turned"
    return False


def embed_aligned(image, face):
    recognizer = _get_sface()
    if recognizer is None:
        return None
    try:
        import numpy as np

        with _sface_lock:
            aligned = recognizer.alignCrop(image, face)
            feature = recognizer.feature(aligned)
        vector = np.asarray(feature, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm <= 0:
            return None
        return (vector / norm).tolist()
    except Exception:
        _logger.exception("SFace embedding failed.")
        return None


def cosine_similarity(left, right):
    if not left or not right or len(left) != len(right):
        return None
    import numpy as np

    a = np.asarray(left, dtype=np.float32)
    b = np.asarray(right, dtype=np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0:
        return None
    return float(np.dot(a, b) / denom)


def compare_embeddings(probe, enrolled):
    """Return (cosine, reason, force_reject).

    Cosine >= 0.45 accept (no HR review).
    0.30-0.45 face_mismatch needs HR verification (punch is still recorded).
    < 0.30 face_low_match recapture (no punch).
    """
    score = cosine_similarity(probe, enrolled)
    if score is None:
        return None, "face_check_unavailable", False
    if score >= COSINE_ACCEPT:
        return score, False, False
    if score >= COSINE_REVIEW:
        return score, "face_mismatch", False
    return score, "face_low_match", True


def packing_embedding(values):
    import numpy as np
    return np.asarray(values, dtype=np.float32).tobytes()


def unpack_embedding(blob):
    if not blob:
        return None
    import numpy as np
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    elif isinstance(blob, str):
        import base64
        try:
            blob = base64.b64decode(blob)
        except (TypeError, ValueError):
            return None
    vector = np.frombuffer(blob, dtype=np.float32)
    if vector.size == 0:
        return None
    return vector.tolist()


def _detect_yunet_faces(image):
    detector = presence._get_yunet_detector()
    if detector is None:
        return None
    try:
        import numpy as np

        height, width = image.shape[:2]
        with presence._lock:
            detector.setInputSize((width, height))
            _retval, faces = detector.detect(image)
    except Exception:
        _logger.exception("YuNet landmark detection failed.")
        return None
    if faces is None or len(faces) == 0:
        return []
    return [row for row in np.atleast_2d(faces)]


def _get_sface():
    global _sface, _sface_failed
    if _sface_failed:
        return None
    if _sface is not None:
        return _sface
    with _sface_lock:
        if _sface_failed:
            return None
        if _sface is not None:
            return _sface
        try:
            import cv2

            presence.configure_cv_threads()
            path = sface_model_path()
            if not os.path.isfile(path):
                _logger.warning("SFace model is missing at %s.", path)
                _sface_failed = True
                return None
            if not hasattr(cv2, "FaceRecognizerSF"):
                _logger.warning("This OpenCV build has no FaceRecognizerSF.")
                _sface_failed = True
                return None
            _sface = cv2.FaceRecognizerSF.create(path, "")
            return _sface
        except Exception:
            _logger.exception("Could not load SFace recognizer.")
            _sface_failed = True
            return None
