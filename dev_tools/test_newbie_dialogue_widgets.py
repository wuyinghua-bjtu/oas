"""Offline widget tests: THREE original captures total, one per named speaker.

All altered images below are synthetic tests, not additional observed frames.
No device, process-control, network, OCR, or game-click calls are imported.
"""

from pathlib import Path
import unittest

import cv2
import numpy as np

from tasks.NewbieLeveling.dialogue_widgets import (
    SCENES, WIDGET_ROIS, WIDGET_ROI_OVERRIDES, observe_dialogue_widgets,
)
from tasks.NewbieLeveling.vision import NewbieVision


FIXTURES = Path(__file__).with_name('fixtures') / 'newbie_leveling'
CAPTURES = {'xiaobai': 'story_dialogue_1280.png',
            'jiumingmao': 'dialogue_widget_cat_1280.png'}


def read_frame(filename):
    frame = cv2.imdecode(np.fromfile(str(FIXTURES / filename), dtype=np.uint8),
                         cv2.IMREAD_COLOR)
    if frame is None:
        raise AssertionError('Missing original dialogue fixture: ' + filename)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def patch_area(frame, area, value):
    x, y, width, height = area
    frame[y:y + height, x:x + width] = value


class NewbieDialogueWidgetTests(unittest.TestCase):
    def setUp(self):
        def forbidden_ocr(*args):
            raise AssertionError('Dialogue widget matching must not use OCR')
        self.vision = NewbieVision(text_reader=forbidden_ocr)
        self.frames = {speaker: read_frame(name) for speaker, name in CAPTURES.items()}

    def observe(self, frame):
        return observe_dialogue_widgets(frame, self.vision)

    def test_exactly_two_original_captures_match_their_speaker_and_inner_controls(self):
        for speaker, frame in self.frames.items():
            with self.subTest(speaker=speaker):
                result = self.observe(frame)
                self.assertIsNotNone(result)
                self.assertEqual(result['page'], 'story_dialogue')
                self.assertEqual(result['story_skip_area'], (846, 564, 48, 20))
                self.assertEqual(result['return_area'], (29, 29, 24, 24))
                self.assertIn('dialogue_widget_' + speaker + '_speaker', result['evidence'])
                self.assertEqual(set(result), {'page', 'story_skip_area', 'return_area',
                                               'evidence', 'reason'})

    def test_allowed_speakers_filter_limits_runtime_to_the_requested_variant(self):
        for allowed in ('xiaobai', 'jiumingmao'):
            for speaker, frame in self.frames.items():
                with self.subTest(allowed=allowed, speaker=speaker):
                    result = observe_dialogue_widgets(frame, self.vision,
                                                       allowed_speakers=(allowed,))
                    if speaker == allowed:
                        self.assertIsNotNone(result)
                    else:
                        self.assertIsNone(result)

    def test_empty_or_unknown_speaker_allowlist_never_adds_a_variant(self):
        for allowed in ((), ('unknown',), ('buy', 'confirm')):
            for frame in self.frames.values():
                self.assertIsNone(observe_dialogue_widgets(
                    frame, self.vision, allowed_speakers=allowed))

    def test_every_widget_and_each_environment_anchor_is_required(self):
        for speaker, original in self.frames.items():
            for name, area in dict(WIDGET_ROIS, **SCENES[speaker]).items():
                with self.subTest(speaker=speaker, missing=name):
                    frame = original.copy()
                    patch_area(frame, area, 0)
                    self.assertIsNone(self.observe(frame))

    def test_black_white_noise_and_invalid_input_have_no_actions(self):
        for frame in (None, np.zeros((720, 1280, 3), np.uint8),
                      np.full((720, 1280, 3), 255, np.uint8),
                      np.zeros((720, 1280), np.uint8),
                      np.zeros((360, 640, 3), np.uint8),
                      np.zeros((720, 1280, 3), float),
                      np.random.default_rng(17).integers(0, 256, (720, 1280, 3),
                                                        dtype=np.uint8)):
            self.assertIsNone(self.observe(frame))

    def test_widgets_pasted_on_black_or_courtyard_are_not_a_story_scene(self):
        courtyard = read_frame('courtyard_1280.png')
        for speaker, original in self.frames.items():
            for background in (np.zeros_like(original), courtyard):
                with self.subTest(speaker=speaker, background_mean=float(background.mean())):
                    frame = background.copy()
                    for area in WIDGET_ROIS.values():
                        x, y, width, height = area
                        patch_area(frame, area, original[y:y + height, x:x + width])
                    self.assertIsNone(self.observe(frame))

    def test_widgets_cannot_cross_the_two_recorded_forest_variants(self):
        for source, destination in (('xiaobai', 'jiumingmao'), ('jiumingmao', 'xiaobai')):
            frame = self.frames[destination].copy()
            for area in WIDGET_ROIS.values():
                x, y, width, height = area
                patch_area(frame, area, self.frames[source][y:y + height, x:x + width])
            self.assertIsNone(self.observe(frame))

    def test_unknown_or_swapped_speaker_is_not_whitelisted(self):
        area = WIDGET_ROIS['speaker']
        x, y, width, height = area
        for speaker, original in self.frames.items():
            other = 'jiumingmao' if speaker == 'xiaobai' else 'xiaobai'
            frame = original.copy()
            patch_area(frame, area, self.frames[other][y:y + height, x:x + width])
            self.assertIsNone(self.observe(frame))
            patch_area(frame, area, (12, 12, 12))
            cv2.putText(frame, 'BUY', (345, 582), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (255, 120, 20), 2)
            self.assertIsNone(self.observe(frame))

    def test_further_dimming_or_brightening_is_not_the_recorded_dark_effect(self):
        for speaker, original in self.frames.items():
            for multiplier in (0.5, 0.8, 0.95, 1.10):
                with self.subTest(speaker=speaker, multiplier=multiplier):
                    frame = np.clip(original.astype(float) * multiplier, 0, 255).astype(np.uint8)
                    self.assertIsNone(self.observe(frame))

    def test_opaque_and_semtransparent_modal_negative_examples(self):
        # These rectangles overlap an independent environment or dialogue
        # anchor. This does not claim arbitrary overlays are detectable.
        for speaker, original in self.frames.items():
            for area in ((450, 170, 440, 370), (320, 535, 650, 160),
                         (200, 90, 240, 270), (350, 280, 580, 280),
                         (500, 370, 340, 240),
                         (10, 10, 1260, 680)):
                for opacity in (0.4, 1.0):
                    with self.subTest(speaker=speaker, area=area, opacity=opacity):
                        frame = original.copy()
                        x, y, width, height = area
                        old = frame[y:y + height, x:x + width].astype(float)
                        color = np.array((220, 200, 165))
                        patch_area(frame, area, (old * (1 - opacity) + color * opacity).astype(np.uint8))
                        self.assertIsNone(self.observe(frame))

    def test_shifted_controls_do_not_authorize_old_screen_coordinates(self):
        for original in self.frames.values():
            frame = original.copy()
            x, y, width, height = WIDGET_ROIS['skip']
            copied = frame[y:y + height, x:x + width].copy()
            patch_area(frame, (x, y, width, height), 0)
            patch_area(frame, (x + 25, y - 60, width, height), copied)
            self.assertIsNone(self.observe(frame))

    def test_synthetic_foreground_pose_change_does_not_fit_whole_frame(self):
        # Explicitly synthetic changed foreground pixels, not a second cat
        # capture nor evidence that arbitrary motion/overlays were observed.
        for original in self.frames.values():
            frame = original.copy()
            patch_area(frame, (560, 310, 110, 175), (45, 90, 150))
            self.assertIsNotNone(self.observe(frame))

    def test_corrupt_or_missing_widget_asset_fails_closed(self):
        class MissingAssets:
            def _template(self, path):
                raise ValueError('offline missing asset')
        self.assertIsNone(observe_dialogue_widgets(self.frames['jiumingmao'], MissingAssets()))


class KaguraDialogueWidgetTests(unittest.TestCase):
    """One real Kagura frame; all modified images are synthetic regressions."""

    def setUp(self):
        def forbidden_ocr(*args):
            raise AssertionError('Kagura dialogue must not invoke OCR')
        self.vision = NewbieVision(text_reader=forbidden_ocr)
        self.frame = read_frame('dialogue_widget_kagura_1280.png')
        self.widgets = dict(WIDGET_ROIS, **WIDGET_ROI_OVERRIDES['kagura'])

    def observe(self, frame, allowed=('kagura',)):
        return observe_dialogue_widgets(frame, self.vision, allowed_speakers=allowed)

    def test_single_original_kagura_frame_has_only_explicit_dialogue_controls(self):
        result = self.observe(self.frame)
        self.assertIsNotNone(result)
        self.assertEqual(result['page'], 'story_dialogue')
        self.assertEqual(result['story_skip_area'], (846, 564, 48, 20))
        self.assertEqual(result['return_area'], (29, 29, 24, 24))
        self.assertEqual(result['reason'], 'verified_kagura_dialogue_widgets')
        self.assertEqual(set(result), {'page', 'story_skip_area', 'return_area',
                                       'evidence', 'reason'})

    def test_kagura_must_be_explicitly_allowed_in_restricted_runtime(self):
        for allowed in ((), ('xiaobai', 'jiumingmao'), ('unknown',)):
            with self.subTest(allowed=allowed):
                self.assertIsNone(self.observe(self.frame, allowed))

    def test_every_kagura_widget_and_three_static_anchors_are_required(self):
        for name, area in dict(self.widgets, **SCENES['kagura']).items():
            with self.subTest(missing=name):
                frame = self.frame.copy()
                patch_area(frame, area, 0)
                self.assertIsNone(self.observe(frame))

    def test_kagura_widgets_on_black_or_another_forest_camera_are_rejected(self):
        for source in (np.zeros_like(self.frame), read_frame('dialogue_widget_cat_1280.png'),
                       read_frame('courtyard_1280.png')):
            frame = source.copy()
            for area in self.widgets.values():
                x, y, width, height = area
                patch_area(frame, area, self.frame[y:y + height, x:x + width])
            self.assertIsNone(self.observe(frame))

    def test_kagura_rejects_unknown_speaker_and_swapped_known_name(self):
        area = WIDGET_ROIS['speaker']
        x, y, width, height = area
        for filename in CAPTURES.values():
            frame = self.frame.copy()
            other = read_frame(filename)
            patch_area(frame, area, other[y:y + height, x:x + width])
            self.assertIsNone(self.observe(frame))
        frame = self.frame.copy()
        patch_area(frame, area, (8, 8, 8))
        cv2.putText(frame, 'BUY', (345, 582), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (255, 120, 20), 2)
        self.assertIsNone(self.observe(frame))

    def test_kagura_dimming_and_observed_style_modal_negatives(self):
        for multiplier in (0.0, 0.5, 0.8, 0.95, 1.10):
            with self.subTest(multiplier=multiplier):
                frame = np.clip(self.frame.astype(float) * multiplier, 0, 255).astype(np.uint8)
                self.assertIsNone(self.observe(frame))
        for area in ((500, 100, 400, 420), (320, 540, 650, 165),
                     (100, 80, 240, 250)):
            for opacity in (0.4, 1.0):
                with self.subTest(area=area, opacity=opacity):
                    frame = self.frame.copy()
                    x, y, width, height = area
                    old = frame[y:y + height, x:x + width].astype(float)
                    patch_area(frame, area, (old * (1 - opacity)
                               + np.array((220, 200, 165)) * opacity).astype(np.uint8))
                    self.assertIsNone(self.observe(frame))

    def test_kagura_synthetic_portrait_change_does_not_become_a_pose_template(self):
        frame = self.frame.copy()
        # This is synthetic, NOT an additional captured portrait/animation.
        # The changed old footer ROI is deliberately outside Kagura's panel.
        patch_area(frame, (0, 310, 325, 410), (25, 40, 70))
        self.assertIsNotNone(self.observe(frame))


if __name__ == '__main__':
    unittest.main()
