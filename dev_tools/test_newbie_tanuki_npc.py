"""Actual post-eye frames through local vision; no game/device access."""
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from tasks.NewbieLeveling.vision import NewbieVision


FIXTURES = Path(__file__).with_name('fixtures') / 'newbie_leveling'


def frame(path):
    return np.array(Image.open(path).convert('RGB'))


class TanukiNpcTests(unittest.TestCase):
    def setUp(self):
        self.vision = NewbieVision(text_reader=lambda *_: None)
        self.paths = sorted((FIXTURES / 'post_eye_tanuki').glob('*.png'))
        self.source = frame(self.paths[0])

    def test_five_recorded_frames_identify_bounded_tanuki_target(self):
        self.assertEqual(len(self.paths), 5)
        for path in self.paths:
            result = self.vision.observe(frame(path))
            self.assertEqual(result.page, 'story_scene', (path, result))
            self.assertEqual(result.npc_story_area, (1110, 225, 20, 18))
            self.assertEqual(result.reason, 'verified_tanuki_story_npc')
            self.assertIsNone(result.level)

    def test_missing_dots_or_ring_does_not_authorize_click(self):
        for area in ((1100,225,39,19),(1090,205,59,60)):
            image = self.source.copy()
            x,y,w,h=area
            image[y:y+h,x:x+w]=0
            self.assertIsNone(self.vision.observe(image).npc_story_area)

    def test_shifted_bubble_is_not_clicked_at_old_position(self):
        image = self.source.copy()
        image[205:265,800:859] = image[205:265,1090:1149]
        image[205:265,1090:1149] = 0
        self.assertIsNone(self.vision.observe(image).npc_story_area)

    def test_two_valid_dialogue_targets_are_rejected(self):
        image = self.source.copy()
        earlier=frame(FIXTURES / 'story_scene_1280.png')
        image[241:301,169:228] = earlier[241:301,169:228]
        self.assertIsNone(self.vision.observe(image).npc_story_area)

    def test_dark_modal_or_unknown_scene_does_not_inherit_target(self):
        for factor in (0.0,0.5,0.85):
            image=(self.source.astype(float)*factor).astype(np.uint8)
            self.assertIsNone(self.vision.observe(image).npc_story_area)
        image=np.zeros_like(self.source)
        image[205:265,1090:1149]=self.source[205:265,1090:1149]
        self.assertIsNone(self.vision.observe(image).npc_story_area)
        image=self.source.copy()
        image[260:550,300:950]=(220,210,180)
        self.assertIsNone(self.vision.observe(image).npc_story_area)


if __name__ == '__main__':
    unittest.main()
