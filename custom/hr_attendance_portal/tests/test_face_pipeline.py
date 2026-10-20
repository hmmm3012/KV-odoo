# -*- coding: utf-8 -*-

import base64
import math

from odoo.tests.common import TransactionCase, tagged

from .common import TINY_JPEG_B64


@tagged("post_install", "-at_install")
class TestFacePipeline(TransactionCase):
    def _require_numpy(self):
        try:
            import numpy as np
            return np
        except ImportError:
            self.skipTest("numpy is not installed")

    def _blank_image(self, height=480, width=640):
        np = self._require_numpy()
        return np.zeros((height, width, 3), dtype=np.uint8)

    def _face(self, w=200, h=200, re=(220, 180), le=(300, 180), nose=(260, 210), score=0.95):
        np = self._require_numpy()
        return np.array([
            160, 80, w, h,
            re[0], re[1], le[0], le[1],
            nose[0], nose[1],
            230, 250, 290, 250,
            score,
        ], dtype=np.float32)

    def test_quality_rejects_tiny_tilted_and_turned_faces(self):
        from odoo.addons.hr_attendance_portal.models.face_pipeline import evaluate_quality

        image = self._blank_image()
        self.assertEqual(evaluate_quality(image, self._face(w=40, h=40)), "face_too_small")
        self.assertEqual(
            evaluate_quality(image, self._face(re=(220, 140), le=(300, 220), nose=(260, 180))),
            "face_tilted",
        )
        self.assertEqual(
            evaluate_quality(image, self._face(nose=(220, 180))),
            "face_turned",
        )
        self.assertFalse(evaluate_quality(image, self._face()))

    def test_cosine_bands_and_packing(self):
        from odoo.addons.hr_attendance_portal.models.face_pipeline import (
            compare_embeddings,
            cosine_similarity,
            packing_embedding,
            unpack_embedding,
        )

        same = [1.0] + [0.0] * 127
        other = [0.0, 1.0] + [0.0] * 126
        self.assertAlmostEqual(cosine_similarity(same, same), 1.0)
        self.assertAlmostEqual(cosine_similarity(same, other), 0.0)

        score, reason, force = compare_embeddings(same, same)
        self.assertGreaterEqual(score, 0.45)
        self.assertFalse(reason)
        self.assertFalse(force)

        mid = [0.36, math.sqrt(1.0 - 0.36 ** 2)] + [0.0] * 126
        score, reason, force = compare_embeddings(same, mid)
        self.assertAlmostEqual(score, 0.36, places=2)
        self.assertEqual(reason, "face_mismatch")
        self.assertFalse(force)

        low = [0.1, math.sqrt(1.0 - 0.1 ** 2)] + [0.0] * 126
        score, reason, force = compare_embeddings(same, low)
        self.assertEqual(reason, "face_low_match")
        self.assertTrue(force)

        unpacked = unpack_embedding(packing_embedding(same))
        self.assertEqual(len(unpacked), 128)
        self.assertAlmostEqual(unpacked[0], 1.0)

    def test_unwraps_odoo_binary_base64_cache_bytes(self):
        from odoo.addons.hr_attendance_portal.models.face_detection import (
            _decode_image,
            unwrap_image_bytes,
        )

        jpeg = base64.b64decode(TINY_JPEG_B64)
        self.assertTrue(unwrap_image_bytes(jpeg).startswith(b"\xff\xd8\xff"))
        self.assertTrue(unwrap_image_bytes(TINY_JPEG_B64).startswith(b"\xff\xd8\xff"))
        self.assertTrue(unwrap_image_bytes(TINY_JPEG_B64.encode()).startswith(b"\xff\xd8\xff"))
        image = _decode_image(TINY_JPEG_B64.encode())
        self.assertIsNotNone(image)
        self.assertEqual(len(image.shape), 3)

    def test_detect_image_is_capped_at_512(self):
        try:
            import cv2  # noqa: F401
        except ImportError:
            self.skipTest("opencv-python-headless is not installed")
        np = self._require_numpy()
        from odoo.addons.hr_attendance_portal.models.face_detection import (
            DETECT_MAX_SIDE,
            _image_for_detect,
        )

        large = np.zeros((1200, 1600, 3), dtype=np.uint8)
        resized = _image_for_detect(large)
        self.assertLessEqual(max(resized.shape[:2]), DETECT_MAX_SIDE)
        small = np.zeros((240, 320, 3), dtype=np.uint8)
        self.assertIs(_image_for_detect(small), small)

    def test_blank_jpeg_has_no_face(self):
        from odoo.addons.hr_attendance_portal.models.face_pipeline import process_face

        result = process_face(base64.b64decode(TINY_JPEG_B64))
        if result.get("unavailable"):
            self.skipTest("opencv-python-headless or YuNet is not available")
        self.assertIn(result["quality_reason"], ("no_face", "face_too_small"))
        self.assertFalse(result.get("embedding"))
