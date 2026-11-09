"""Recorded story re-entry frames and in-memory negatives; no device access."""
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from tasks.NewbieLeveling.vision import NewbieVision


FIXTURES = Path(__file__).with_name('fixtures') / 'newbie_leveling'


def frame(path):
    return np.array(Image.open(path).convert('RGB'))


class StoryReentryTests(unittest.TestCase):
    def setUp(self):
        self.vision = NewbieVision(text_reader=lambda *_: None)
        self.paths = sorted((FIXTURES / 'story_reentry').glob('*.png'))
        self.source = frame(self.paths[0])

    def test_six_recorded_frames_identify_bounded_reentry_target(self):
        self.assertEqual(len(self.paths), 6)
        for path in self.paths:
            with self.subTest(frame=path.name):
                result = self.vision.observe(frame(path))
                self.assertEqual(result.page, 'story_scene', result)
                self.assertEqual(result.reason, 'verified_reentry_story_npc')
                self.assertIsNotNone(result.npc_story_area)
                x, y, width, height = result.npc_story_area
                self.assertIn(x, range(473, 477))
                self.assertIn(y, range(317, 321))
                self.assertEqual((width, height), (20, 18))
                self.assertIsNone(result.level)
                self.assertIsNone(result.identity)
                self.assertIsNone(result.story_skip_area)
                self.assertIsNone(result.tutorial_area)

    def test_missing_dots_or_ring_does_not_authorize_npc(self):
        for missing in ('dots', 'ring'):
            with self.subTest(missing=missing):
                image = self.source.copy()
                bubble = image[298:358, 453:512]
                if missing == 'dots':
                    bubble[20:39, 10:49] = 0
                else:
                    yy, xx = np.ogrid[:60, :59]
                    radius = np.sqrt((xx - 59 / 2) ** 2 + (yy - 60 / 2) ** 2)
                    bubble[(radius >= 22) & (radius <= 30)] = 0
                self.assertIsNone(self.vision.observe(image).npc_story_area)

    def test_second_tanuki_or_old_left_bubble_rejects_all_actions(self):
        tanuki = frame(sorted((FIXTURES / 'post_eye_tanuki').glob('*.png'))[0])
        old_left = frame(FIXTURES / 'story_scene_1280.png')
        for name, donor, area in (
            ('tanuki', tanuki, (1090, 205, 59, 60)),
            ('old_left', old_left, (169, 241, 59, 60)),
        ):
            with self.subTest(second=name):
                image = self.source.copy()
                x, y, width, height = area
                image[y:y + height, x:x + width] = donor[y:y + height, x:x + width]
                scene = self.vision.observe_story_scene(image)
                self.assertIsNotNone(scene)
                self.assertEqual(scene.reason, 'story_scene_multiple_npcs', scene)
                result = self.vision.observe(image)
                self.assertEqual(result.page, 'unknown', result)
                self.assertIsNone(result.npc_story_area)
                self.assertIsNone(result.return_area)
                self.assertIsNone(result.story_skip_area)
                self.assertIsNone(result.tutorial_area)

    def test_bubble_moved_outside_search_roi_does_not_authorize_npc(self):
        image = self.source.copy()
        image[298:358, 800:859] = image[298:358, 453:512]
        image[298:358, 453:512] = 0
        self.assertIsNone(self.vision.observe(image).npc_story_area)

    def test_dark_covered_or_unknown_scene_does_not_inherit_npc(self):
        for factor in (0.0, 0.5, 0.85):
            with self.subTest(brightness=factor):
                image = (self.source.astype(float) * factor).astype(np.uint8)
                self.assertIsNone(self.vision.observe(image).npc_story_area)
        image = self.source.copy()
        image[260:550, 300:950] = (220, 210, 180)
        self.assertIsNone(self.vision.observe(image).npc_story_area)
        image = np.zeros_like(self.source)
        image[298:358, 453:512] = self.source[298:358, 453:512]
        self.assertIsNone(self.vision.observe(image).npc_story_area)


if __name__ == '__main__':
    unittest.main()
