import unittest
from unittest.mock import patch

import cv2
import numpy as np

from tasks.Mentorship.vision import detect


class SoulsReturnTests(unittest.TestCase):
    def test_selected_layer_matches_when_color_changes(self):
        generator = np.random.default_rng(42)
        gray = generator.integers(40, 180, (30, 100), dtype=np.uint8)
        template = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        tinted = template.copy()
        tinted[:, :, 2] += 60
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        image[105:135, 100:200] = cv2.cvtColor(tinted, cv2.COLOR_BGR2RGB)
        with patch('tasks.Mentorship.vision.np.fromfile', return_value=np.array([1])), \
             patch('tasks.Mentorship.vision.cv2.imdecode', return_value=template):
            self.assertIsNotNone(detect(image, 'orochi_selected_one'))

    def test_unknown_screen_is_not_selected_layer(self):
        generator = np.random.default_rng(42)
        template = generator.integers(0, 255, (30, 100, 3), dtype=np.uint8)
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        with patch('tasks.Mentorship.vision.np.fromfile', return_value=np.array([1])), \
             patch('tasks.Mentorship.vision.cv2.imdecode', return_value=template):
            self.assertIsNone(detect(image, 'orochi_selected_one'))


if __name__ == '__main__':
    unittest.main()
