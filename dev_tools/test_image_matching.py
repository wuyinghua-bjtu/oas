"""Offline tests for multi-scale match bounds and click coordinates."""

import unittest
from unittest.mock import patch

import cv2
import numpy as np

from module.atom.image import RuleImage


class MultiScaleMatchTests(unittest.TestCase):
    def setUp(self):
        self.rule = RuleImage(
            (3, 4, 40, 30), (20, 30, 100, 100),
            'Template matching', 0.8, 'synthetic_template.png',
        )
        self.rule._image = np.random.default_rng(731).integers(
            0, 256, size=(30, 40, 3), dtype=np.uint8,
        )
        self.frame = np.zeros((160, 160, 3), dtype=np.uint8)

    def match_with_scores(self, scores, scales=(0.5, 1.0, 1.2)):
        results = [(0.0, score, (0, 0), (7, 11)) for score in scores]
        with patch('module.atom.image.cv2.minMaxLoc', side_effect=results):
            return self.rule.match_multi_scale(self.frame, scales=scales)

    def test_real_best_scale_before_final_scale_has_correct_bounds_and_center(self):
        # Only the half-size template is embedded; later scales must not
        # overwrite its click dimensions. No asset files or device are used.
        template = cv2.resize(self.rule.image, (20, 15))
        self.frame[41:56, 27:47] = template

        self.assertTrue(self.rule.match_multi_scale(self.frame, scales=[0.5, 1.0, 1.2]))
        self.assertEqual(self.rule.roi_front, [27, 41, 20, 15])
        self.assertEqual(self.rule.front_center(), (37, 48))

    def test_middle_best_scale_has_its_own_dimensions(self):
        self.assertTrue(self.match_with_scores([0.4, 0.95, 0.5]))
        self.assertEqual(self.rule.roi_front, [27, 41, 40, 30])
        self.assertEqual(self.rule.front_center(), (47, 56))

    def test_final_best_scale_keeps_existing_success_behavior(self):
        self.assertTrue(self.match_with_scores([0.4, 0.5, 0.95]))
        self.assertEqual(self.rule.roi_front, [27, 41, 48, 36])
        self.assertEqual(self.rule.front_center(), (51, 59))

    def test_failed_later_scale_does_not_replace_best_dimensions(self):
        matches = [np.ones((1, 1)), cv2.error('Later scale unavailable')]
        with patch('module.atom.image.cv2.matchTemplate', side_effect=matches), \
                patch('module.atom.image.cv2.minMaxLoc', return_value=(0.0, 0.95, (0, 0), (7, 11))):
            self.assertTrue(self.rule.match_multi_scale(self.frame, scales=[0.5, 1.2]))
        self.assertEqual(self.rule.roi_front, [27, 41, 20, 15])
        self.assertEqual(self.rule.front_center(), (37, 48))

    def test_below_threshold_does_not_mutate_bounds(self):
        original = self.rule.roi_front.copy()
        self.assertFalse(self.match_with_scores([0.4, 0.8, 0.5]))
        self.assertEqual(self.rule.roi_front, original)

    def test_no_valid_scales_does_not_mutate_bounds(self):
        original = self.rule.roi_front.copy()
        for scales in ([], [0.1, 0.2]):
            with self.subTest(scales=scales):
                self.assertFalse(self.rule.match_multi_scale(self.frame, scales=scales))
                self.assertEqual(self.rule.roi_front, original)


if __name__ == '__main__':
    unittest.main()
