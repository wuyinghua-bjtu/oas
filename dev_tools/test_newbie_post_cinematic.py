"""Offline tests of recorded post-movie NPC frames. No OCR/device inputs."""
from pathlib import Path
import unittest

import cv2
import numpy as np
from PIL import Image

from tasks.NewbieLeveling.post_cinematic import (
    BUBBLE_ROI, SCENE_ROIS, POST_DIALOGUE_BUBBLE_ROI,
    POST_DIALOGUE_SCENE_ROIS, observe_post_cinematic,
)
from tasks.NewbieLeveling.vision import NewbieVision

FIXTURES = Path(__file__).with_name('fixtures') / 'newbie_leveling'


def read(name):
    return np.array(Image.open(FIXTURES / name).convert('RGB'))


class PostCinematicTests(unittest.TestCase):
    def setUp(self):
        self.vision = NewbieVision(text_reader=lambda *args: self.fail('No OCR on NPC scene'))
        self.original = read('cinematic/cinematic_post_tanuki_02_1280.png')

    def assert_rejected(self, frame):
        self.assertIsNone(observe_post_cinematic(frame, self.vision))
        result = self.vision.observe(frame)
        for name in ('npc_story_area', 'return_area', 'story_skip_area', 'tutorial_area'):
            self.assertIsNone(getattr(result, name))

    def test_original_and_five_independent_later_captures(self):
        frames = [self.original, read('cinematic/cinematic_post_tanuki_01_1280.png')]
        frames += [read('post_cinematic/' + path.name)
                   for path in sorted((FIXTURES / 'post_cinematic').glob('*.png'))]
        self.assertGreaterEqual(len(frames), 7)
        for frame in frames:
            result = self.vision.observe(frame)
            self.assertEqual(result.page, 'story_scene')
            self.assertEqual(result.reason, 'verified_post_cinematic_umbrella_npc')
            self.assertTrue(490 <= result.npc_story_area[0] <= 491)
            self.assertEqual(result.return_area, (29, 29, 24, 24))
            self.assertIsNone(result.level)
            self.assertIsNone(result.identity)

    def test_each_anchor_and_back_are_required(self):
        for x, y, w, h in [*SCENE_ROIS.values(), (15, 15, 54, 55)]:
            frame = self.original.copy()
            frame[y:y+h, x:x+w] = 0
            self.assert_rejected(frame)

    def test_missing_dots_ring_and_entire_bubble_are_rejected(self):
        for x, y, w, h in ((480, 304, 40, 15), (470, 282, 60, 20), BUBBLE_ROI):
            frame = self.original.copy()
            frame[y:y+h, x:x+w] = 0
            self.assert_rejected(frame)

    def test_second_npc_and_displaced_target_are_rejected(self):
        x, y, w, h = BUBBLE_ROI
        bubble = self.original[y:y+h, x:x+w]
        for erase_original in (False, True):
            frame = self.original.copy()
            if erase_original:
                frame[y:y+h, x:x+w] = 0
            frame[285:285+h, 840:840+w] = bubble
            self.assert_rejected(frame)

    def test_dimming_and_modal_over_samples_are_rejected(self):
        for factor in (.5, .8, .95):
            self.assert_rejected((self.original.astype(float) * factor).astype(np.uint8))
        for x, y, w, h in ((350, 280, 580, 280), (200, 90, 240, 270),
                           (0, 540, 1280, 180)):
            frame = self.original.copy()
            frame[y:y+h, x:x+w] = (222, 208, 180)
            cv2.putText(frame, 'BUY / LOGIN', (x+10, y+40), cv2.FONT_HERSHEY_SIMPLEX,
                        .8, (40, 20, 10), 2)
            self.assert_rejected(frame)

    def test_movie_and_black_are_not_npc_pages(self):
        self.assert_rejected(read('cinematic/cinematic_paused_1280.png'))
        self.assert_rejected(np.zeros_like(self.original))

    def test_bad_geometry_and_missing_assets_fail_closed(self):
        for frame in (None, self.original[:360], self.original.astype(float)):
            self.assertIsNone(observe_post_cinematic(frame, self.vision))
        class Missing:
            def _match(self, *args, **kwargs):
                raise ValueError('Missing asset')
        self.assertIsNone(observe_post_cinematic(self.original, Missing()))


class PostDialogueTests(unittest.TestCase):
    def setUp(self):
        self.vision = NewbieVision(text_reader=lambda *args: self.fail('No OCR on NPC scene'))
        self.paths = sorted((FIXTURES / 'post_dialogue').glob('*.png'))
        self.original = read('post_dialogue/' + self.paths[0].name)

    def assert_rejected(self, frame):
        self.assertIsNone(observe_post_cinematic(frame, self.vision))
        result = self.vision.observe(frame)
        for name in ('npc_story_area', 'return_area', 'story_skip_area', 'tutorial_area'):
            self.assertIsNone(getattr(result, name))

    def test_three_real_post_dialogue_frames_identify_right_tanuki(self):
        self.assertEqual(len(self.paths), 3)
        for path in self.paths:
            with self.subTest(frame=path.name):
                result = self.vision.observe(read('post_dialogue/' + path.name))
                self.assertEqual(result.page, 'story_scene')
                self.assertEqual(result.reason, 'verified_post_dialogue_tanuki_npc')
                self.assertEqual(result.npc_story_area, (1206, 224, 20, 18))
                self.assertEqual(result.return_area, (29, 29, 24, 24))
                self.assertIsNone(result.level)
                self.assertIsNone(result.identity)

    def test_camera4_requires_each_independent_anchor_floor_and_back(self):
        for area in [*POST_DIALOGUE_SCENE_ROIS.values(), (15, 15, 54, 55)]:
            with self.subTest(missing=area):
                frame = self.original.copy()
                x, y, w, h = area
                frame[y:y+h, x:x+w] = 0
                self.assert_rejected(frame)

    def test_camera4_missing_dots_ring_bubble_or_displaced_target_is_rejected(self):
        for area in ((1196, 224, 40, 19), (1186, 204, 60, 20),
                     POST_DIALOGUE_BUBBLE_ROI):
            with self.subTest(missing=area):
                frame = self.original.copy()
                x, y, w, h = area
                frame[y:y+h, x:x+w] = 0
                self.assert_rejected(frame)
        frame = self.original.copy()
        x, y, w, h = POST_DIALOGUE_BUBBLE_ROI
        frame[204:204+h, 1000:1000+w] = frame[y:y+h, x:x+w]
        frame[y:y+h, x:x+w] = 0
        self.assert_rejected(frame)

    def test_camera4_dimming_modal_and_bubble_without_scene_are_rejected(self):
        for factor in (.5, .8, .95):
            with self.subTest(brightness=factor):
                self.assert_rejected((self.original.astype(float) * factor).astype(np.uint8))
        for x, y, w, h in ((350, 280, 580, 360), (0, 540, 1280, 180)):
            frame = self.original.copy()
            frame[y:y+h, x:x+w] = (222, 208, 180)
            self.assert_rejected(frame)
        frame = np.zeros_like(self.original)
        x, y, w, h = POST_DIALOGUE_BUBBLE_ROI
        frame[y:y+h, x:x+w] = self.original[y:y+h, x:x+w]
        self.assert_rejected(frame)


if __name__ == '__main__':
    unittest.main()
