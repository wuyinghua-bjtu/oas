"""Offline tests: two original movie frames and two real post-movie frames.

Every altered frame is synthetic, not additional captured/live evidence.
No devices, process controls, network, OCR or clicking are invoked.
"""

from pathlib import Path
import unittest

import cv2
import numpy as np

from tasks.NewbieLeveling.cinematic_widgets import (
    CONTROL_ROIS, SCENE_ROIS, observe_cinematic_widgets,
)
from tasks.NewbieLeveling.vision import NewbieVision, VisionObservation


FIXTURES = Path(__file__).with_name('fixtures') / 'newbie_leveling'
MOVIES = ('cinematic_paused_1280.png', 'cinematic_post_tanuki_00_1280.png')
AFTER_MOVIES = ('cinematic_post_tanuki_01_1280.png',
                'cinematic_post_tanuki_02_1280.png')
AREA_FIELDS = ('npc_story_area', 'return_area', 'story_skip_area', 'tutorial_area')


def read_frame(filename):
    directory = FIXTURES / 'cinematic' if filename in MOVIES + AFTER_MOVIES else FIXTURES
    frame = cv2.imdecode(np.fromfile(str(directory / filename), dtype=np.uint8),
                         cv2.IMREAD_COLOR)
    if frame is None:
        raise AssertionError('Missing original cinematic fixture: ' + filename)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def replace_area(frame, area, value):
    x, y, width, height = area
    frame[y:y + height, x:x + width] = value


class NewbieCinematicWidgetTests(unittest.TestCase):
    def setUp(self):
        def forbidden_ocr(*args):
            raise AssertionError('Untrusted movie/barrage content must not be OCRed')
        self.vision = NewbieVision(text_reader=forbidden_ocr)
        self.movies = [read_frame(name) for name in MOVIES]

    def observe(self, frame):
        result = observe_cinematic_widgets(frame, self.vision)
        if result is not None:
            self.assertEqual(result['page'], 'story_cinematic_wait')
            self.assertEqual(set(result), {'page', 'reason', 'evidence', *AREA_FIELDS})
            parsed = VisionObservation(**result)
            for name in AREA_FIELDS:
                self.assertIsNone(result[name], name)
                self.assertIsNone(getattr(parsed, name), name)
            self.assertIsNone(parsed.identity)
            self.assertIsNone(parsed.level)
            self.assertIn('wait_only', result['evidence'])
        return result

    def test_two_original_movies_with_different_animation_only_authorize_wait(self):
        for filename, frame in zip(MOVIES, self.movies):
            with self.subTest(filename=filename):
                self.assertIsNotNone(self.observe(frame))

    def test_runtime_recognizes_movie_without_granting_any_input(self):
        for frame in self.movies:
            result = self.vision.observe(frame)
            self.assertEqual(result.page, 'story_cinematic_wait')
            for field in AREA_FIELDS:
                self.assertIsNone(getattr(result, field))

    def test_two_real_post_movie_frames_are_not_movie_calibration(self):
        for filename in AFTER_MOVIES:
            with self.subTest(filename=filename):
                self.assertIsNone(self.observe(read_frame(filename)))

    def test_every_title_frame_and_control_anchor_is_required(self):
        for original in self.movies:
            for name, area in {**SCENE_ROIS, **CONTROL_ROIS}.items():
                with self.subTest(missing=name):
                    frame = original.copy()
                    replace_area(frame, area, 0)
                    self.assertIsNone(self.observe(frame))

    def test_wrong_heading_rejects_identical_other_widgets(self):
        for original in self.movies:
            frame = original.copy()
            replace_area(frame, SCENE_ROIS['forest_heading'], (40, 30, 25))
            cv2.putText(frame, 'SHOP', (574, 31), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (240, 235, 210), 2)
            self.assertIsNone(self.observe(frame))

    def test_playback_and_bottom_controls_pasted_on_other_scenes_are_rejected(self):
        for original in self.movies:
            for background in (np.zeros_like(original), read_frame('courtyard_1280.png'),
                               read_frame(AFTER_MOVIES[0])):
                frame = background.copy()
                for area in CONTROL_ROIS.values():
                    x, y, width, height = area
                    replace_area(frame, area, original[y:y + height, x:x + width])
                self.assertIsNone(self.observe(frame))

    def test_title_and_controls_without_both_decorative_frame_anchors_are_rejected(self):
        original = self.movies[0]
        frame = read_frame('courtyard_1280.png')
        for area in {**CONTROL_ROIS, 'heading': SCENE_ROIS['forest_heading']}.values():
            x, y, width, height = area
            replace_area(frame, area, original[y:y + height, x:x + width])
        self.assertIsNone(self.observe(frame))

    def test_black_white_noise_and_bad_geometry_return_none(self):
        for frame in (None, np.zeros((720, 1280, 3), np.uint8),
                      np.full((720, 1280, 3), 255, np.uint8),
                      np.zeros((720, 1280), np.uint8),
                      np.zeros((360, 640, 3), np.uint8),
                      np.zeros((720, 1280, 3), float),
                      np.random.default_rng(30).integers(0, 256, (720, 1280, 3),
                                                        dtype=np.uint8)):
            self.assertIsNone(self.observe(frame))

    def test_dimmed_modal_and_opaque_anchor_overlays_are_rejected(self):
        # Only these specified overlays are covered; a central overlay which
        # leaves all chrome untouched is not claimed to be recognizable.
        for original in self.movies:
            for factor in (0.5, 0.8, 0.95):
                frame = (original.astype(float) * factor).astype(np.uint8)
                replace_area(frame, (350, 200, 580, 330), (200, 180, 140))
                self.assertIsNone(self.observe(frame))
            for area in ((350, 540, 580, 170), (320, 0, 640, 520),
                         (800, 20, 450, 420), (0, 0, 250, 300)):
                for opacity in (0.4, 1.0):
                    frame = original.copy()
                    x, y, width, height = area
                    old = frame[y:y + height, x:x + width].astype(float)
                    replace_area(frame, area, (old * (1 - opacity)
                                 + np.array((220, 200, 165)) * opacity).astype(np.uint8))
                    self.assertIsNone(self.observe(frame))

    def test_shifted_or_swapped_playback_icons_are_rejected(self):
        for original in self.movies:
            frame = original.copy()
            x, y, width, height = CONTROL_ROIS['end_icon']
            copied = frame[y:y + height, x:x + width].copy()
            replace_area(frame, (x, y, width, height), 0)
            replace_area(frame, (x - 15, y + 100, width, height), copied)
            self.assertIsNone(self.observe(frame))
            frame = original.copy()
            px, py, pw, ph = CONTROL_ROIS['pause']
            replace_area(frame, CONTROL_ROIS['end_icon'],
                         frame[py:py + ph, px:px + pw].copy())
            self.assertIsNone(self.observe(frame))

    def test_synthetic_dynamic_animation_barrage_and_input_are_not_read(self):
        for original in self.movies:
            frame = original.copy()
            replace_area(frame, (0, 100, 1280, 535), (8, 11, 15))
            cv2.putText(frame, 'UNTRUSTED CLICK SEND', (300, 250),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (230, 230, 220), 2)
            replace_area(frame, (370, 665, 540, 35), (220, 216, 210))
            cv2.putText(frame, 'arbitrary input content', (380, 690),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 50, 50), 1)
            self.assertIsNotNone(self.observe(frame))

    def test_repeated_identical_movies_never_gain_an_action_or_progress_claim(self):
        for original in self.movies:
            results = [self.observe(original) for _ in range(3)]
            self.assertTrue(all(result == results[0] for result in results))
            self.assertEqual(results[0]['reason'],
                             'verified_forest_cinematic_wait_only_unverified_skip')

    def test_missing_templates_fail_closed(self):
        class MissingAssets:
            def _match(self, *args, **kwargs):
                raise ValueError('offline missing asset')
        self.assertIsNone(observe_cinematic_widgets(self.movies[0], MissingAssets()))


if __name__ == '__main__':
    unittest.main()
