"""Offline regressions for the recorded dark-scene eye-close prompt.

The three source captures are copied verbatim. Adversarial variants exist only
in test memory; no device calls and no newly generated UI templates are used.
"""

from pathlib import Path
import unittest

import cv2
import numpy as np

from tasks.NewbieLeveling.reveal_widgets import observe_reveal_widgets
from tasks.NewbieLeveling.vision import NewbieVision


FIXTURES = Path(__file__).with_name('fixtures') / 'newbie_leveling'
CAPTURES = FIXTURES / 'reveal_eye_close'
FIRST_CAPTURE = '1788880999139126900-00.png'


def load_frame(path):
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise AssertionError('Missing fixture: ' + str(path))
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


class RevealEyeTests(unittest.TestCase):
    def setUp(self):
        self.vision = NewbieVision()

    def source(self):
        return load_frame(CAPTURES / FIRST_CAPTURE)

    def assert_rejected(self, image):
        result = observe_reveal_widgets(image, self.vision)
        self.assertIsNotNone(result)
        self.assertEqual(result['page'], 'unknown', result)
        self.assertIsNone(result.get('tutorial_area'))
        self.assertIsNone(result.get('npc_story_area'))

    def test_all_three_real_dark_eye_close_frames(self):
        paths = sorted(CAPTURES.glob('*.png'))
        self.assertEqual(len(paths), 3)
        for path in paths:
            with self.subTest(frame=path.name):
                image = load_frame(path)
                result = observe_reveal_widgets(image, self.vision)
                self.assertEqual(result['page'], 'story_eye', result)
                self.assertEqual(result['tutorial_area'], (618, 140, 44, 34))
                self.assertEqual(result['return_area'], (29, 29, 24, 24))
                self.assertIsNone(result.get('npc_story_area'))
                visual = self.vision.observe(image)
                self.assertEqual(visual.page, 'story_eye')
                self.assertEqual(visual.tutorial_area, (618, 140, 44, 34))

    def test_eye_occlusion_is_not_an_action(self):
        image = self.source()
        image[89:223, 574:706] = 0
        self.assert_rejected(image)

    def test_missing_gold_ring_is_not_an_action(self):
        image = self.source()
        eye = image[89:223, 574:706]
        yy, xx = np.mgrid[:134, :132]
        radius = np.sqrt((xx - 66) ** 2 + (yy - 67) ** 2)
        eye[(radius >= 55) & (radius <= 70)] = 0
        self.assert_rejected(image)

    def test_missing_white_eye_symbol_is_not_an_action(self):
        image = self.source()
        eye = image[89:223, 574:706]
        symbol = eye[40:95, 35:100]
        symbol[symbol.min(axis=2) > 170] = 0
        self.assert_rejected(image)

    def test_large_modal_cover_is_not_an_action(self):
        image = self.source()
        image[250:700, 200:1080] = (220, 210, 180)
        self.assert_rejected(image)

    def test_question_and_eye_conflict_is_rejected(self):
        image = self.source()
        question_source = load_frame(FIXTURES / 'story_reveal_1280.png')
        image[264:329, 870:929] = question_source[264:329, 870:929]
        self.assert_rejected(image)


if __name__ == '__main__':
    unittest.main()
