"""Offline wait-only tests, using three original dialogue captures.

Speaker/text substitutions and other altered images are synthetic tests, not
additional real captures or evidence of live/autonomous story progression.
"""

from pathlib import Path
import unittest

import cv2
import numpy as np

from tasks.NewbieLeveling.dialogue_wait import observe_dialogue_wait
from tasks.NewbieLeveling.dialogue_widgets import (
    SCENES, WIDGET_ROIS, WIDGET_ROI_OVERRIDES,
)
from tasks.NewbieLeveling.vision import NewbieVision, VisionObservation


FIXTURES = Path(__file__).with_name('fixtures') / 'newbie_leveling'
CAPTURES = {'xiaobai': 'story_dialogue_1280.png',
            'jiumingmao': 'dialogue_widget_cat_1280.png',
            'kagura': 'dialogue_widget_kagura_1280.png'}
AREA_FIELDS = ('npc_story_area', 'return_area', 'story_skip_area', 'tutorial_area')


def read_frame(filename):
    frame = cv2.imdecode(np.fromfile(str(FIXTURES / filename), dtype=np.uint8),
                         cv2.IMREAD_COLOR)
    if frame is None:
        raise AssertionError('Missing original fixture: ' + filename)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def replace_area(frame, area, value):
    x, y, width, height = area
    frame[y:y + height, x:x + width] = value


class NewbieDialogueWaitTests(unittest.TestCase):
    def setUp(self):
        self.ocr_calls = []
        def forbidden_ocr(*args):
            self.ocr_calls.append(args)
            raise AssertionError('Wait-only matching must not read any OCR')
        self.vision = NewbieVision(text_reader=forbidden_ocr)
        self.frames = {name: read_frame(file) for name, file in CAPTURES.items()}

    def observe(self, frame):
        result = observe_dialogue_wait(frame, self.vision)
        if result is not None:
            # Every test, including synthetic negatives, enforces no actions.
            self.assertEqual(result['page'], 'story_dialogue_wait')
            self.assertEqual(set(result), {'page', 'reason', 'evidence', *AREA_FIELDS})
            for field in AREA_FIELDS:
                self.assertIsNone(result[field], field)
            parsed = VisionObservation(**result)
            self.assertIsNone(parsed.identity)
            self.assertIsNone(parsed.level)
        self.assertEqual(self.ocr_calls, [])
        return result

    def test_three_original_normal_and_dark_dialogues_offer_wait_only(self):
        for variant, frame in self.frames.items():
            with self.subTest(variant=variant):
                self.assertIsNotNone(self.observe(frame))

    def test_synthetic_unknown_speaker_and_changed_dialogue_still_only_wait(self):
        for variant, original in self.frames.items():
            with self.subTest(variant=variant):
                frame = original.copy()
                replace_area(frame, WIDGET_ROIS['speaker'], (8, 8, 8))
                cv2.putText(frame, 'UNKNOWN', (340, 580), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (255, 120, 20), 2)
                replace_area(frame, (340, 614, 570, 34), (8, 8, 8))
                cv2.putText(frame, 'different text, no action', (345, 637),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 225, 210), 1)
                self.assertIsNotNone(self.observe(frame))

    def test_blank_name_or_complete_absence_of_text_is_not_an_action(self):
        for original in self.frames.values():
            frame = original.copy()
            replace_area(frame, WIDGET_ROIS['speaker'], 0)
            replace_area(frame, (340, 614, 570, 34), 0)
            self.assertIsNotNone(self.observe(frame))

    def test_runtime_keeps_exact_known_skips_ahead_of_passive_wait(self):
        for frame in self.frames.values():
            result = self.vision.observe(frame)
            self.assertEqual(result.page, 'story_dialogue')
            self.assertIsNotNone(result.story_skip_area)

    def test_runtime_unknown_speaker_never_gets_a_skip_or_return(self):
        for original in self.frames.values():
            frame = original.copy()
            replace_area(frame, WIDGET_ROIS['speaker'], 0)
            result = self.vision.observe(frame)
            self.assertEqual(result.page, 'story_dialogue_wait')
            for field in AREA_FIELDS:
                self.assertIsNone(getattr(result, field))

    def test_all_scene_anchors_back_skip_divider_and_blank_footer_are_required(self):
        for variant, original in self.frames.items():
            widgets = dict(WIDGET_ROIS, **WIDGET_ROI_OVERRIDES.get(variant, {}))
            required = dict(SCENES[variant], **{name: widgets[name]
                            for name in ('return', 'skip', 'divider', 'panel')})
            for name, area in required.items():
                with self.subTest(variant=variant, missing=name):
                    frame = original.copy()
                    replace_area(frame, area, 0)
                    self.assertIsNone(self.observe(frame))

    def test_black_white_noise_and_bad_geometry_return_none(self):
        for frame in (None, np.zeros((720, 1280, 3), np.uint8),
                      np.full((720, 1280, 3), 255, np.uint8),
                      np.zeros((720, 1280), np.uint8),
                      np.zeros((360, 640, 3), np.uint8),
                      np.zeros((720, 1280, 3), float),
                      np.random.default_rng(21).integers(0, 256, (720, 1280, 3),
                                                        dtype=np.uint8)):
            self.assertIsNone(self.observe(frame))

    def test_pasted_widgets_on_black_or_courtyard_are_not_dialogue_wait(self):
        courtyard = read_frame('courtyard_1280.png')
        for variant, original in self.frames.items():
            widgets = dict(WIDGET_ROIS, **WIDGET_ROI_OVERRIDES.get(variant, {}))
            for background in (np.zeros_like(original), courtyard):
                frame = background.copy()
                for area in widgets.values():
                    x, y, width, height = area
                    replace_area(frame, area, original[y:y + height, x:x + width])
                self.assertIsNone(self.observe(frame))

    def test_further_dimming_does_not_inherit_dark_scene_permission(self):
        for original in self.frames.values():
            for factor in (0.5, 0.8, 0.95):
                frame = (original.astype(float) * factor).astype(np.uint8)
                self.assertIsNone(self.observe(frame))

    def test_missing_templates_cannot_produce_an_observation(self):
        class MissingAssets:
            def _match(self, *args, **kwargs):
                raise ValueError('offline missing template')
        for frame in self.frames.values():
            self.assertIsNone(observe_dialogue_wait(frame, MissingAssets()))

    def test_repeated_identical_frames_never_gain_an_action_or_progress_claim(self):
        for original in self.frames.values():
            results = [self.observe(original) for _ in range(4)]
            self.assertTrue(all(result == results[0] for result in results))
            self.assertEqual(results[0]['reason'], 'verified_forest_dialogue_wait_only')
            self.assertIn('speaker_and_text_unverified', results[0]['evidence'])


if __name__ == '__main__':
    unittest.main()
