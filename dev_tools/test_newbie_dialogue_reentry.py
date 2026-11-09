"""One real Xiaobai action frame and one real Seimei wait-only holdout.

All modified images are synthetic regressions, not more captured evidence.
No OCR, device operations or runtime/runner changes are involved.
"""

from pathlib import Path
import unittest

import cv2
import numpy as np

from tasks.NewbieLeveling.dialogue_wait import observe_dialogue_wait
from tasks.NewbieLeveling.dialogue_widgets import (
    SCENES, WIDGET_ROIS, WIDGET_ROI_OVERRIDES, observe_dialogue_widgets,
)
from tasks.NewbieLeveling.vision import NewbieVision, VisionObservation


FIXTURES = Path(__file__).with_name('fixtures') / 'newbie_leveling'
VARIANT = 'xiaobai_reentry'
AREAS = ('npc_story_area', 'return_area', 'story_skip_area', 'tutorial_area')


def read_frame(name):
    raw = cv2.imdecode(np.fromfile(str(FIXTURES / name), dtype=np.uint8),
                       cv2.IMREAD_COLOR)
    if raw is None:
        raise AssertionError('Missing real re-entry dialogue fixture: ' + name)
    return cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)


def replace_area(frame, area, value):
    x, y, width, height = area
    frame[y:y + height, x:x + width] = value


class NewbieDialogueReentryTests(unittest.TestCase):
    def setUp(self):
        def forbidden_ocr(*args):
            raise AssertionError('Re-entry dialogue must not read OCR')
        self.vision = NewbieVision(text_reader=forbidden_ocr)
        self.xiaobai = read_frame('dialogue_widget_xiaobai_reentry_1280.png')
        self.seimei = read_frame('dialogue_widget_seimei_reentry_1280.png')
        self.widgets = {**WIDGET_ROIS, **WIDGET_ROI_OVERRIDES[VARIANT]}

    def observe(self, frame, allowed=(VARIANT,)):
        return observe_dialogue_widgets(frame, self.vision, allowed_speakers=allowed)

    def test_single_original_xiaobai_has_explicit_skip_only_when_variant_allowed(self):
        result = self.observe(self.xiaobai)
        self.assertIsNotNone(result)
        parsed = VisionObservation(**result)
        self.assertEqual(parsed.page, 'story_dialogue')
        self.assertEqual(parsed.story_skip_area, (846, 564, 48, 20))
        self.assertEqual(parsed.return_area, (29, 29, 24, 24))
        self.assertIsNone(parsed.npc_story_area)
        self.assertIsNone(parsed.tutorial_area)
        self.assertEqual(len(result['evidence']), 8)
        self.assertIn('dialogue_widget_xiaobai_reentry_speaker', result['evidence'])
        for allowed in ((), ('xiaobai',), ('jiumingmao', 'kagura'), ('seimei',)):
            self.assertIsNone(self.observe(self.xiaobai, allowed))

    def test_real_seimei_unknown_speaker_is_passive_wait_with_no_actions(self):
        self.assertIsNone(observe_dialogue_widgets(self.seimei, self.vision))
        result = observe_dialogue_wait(self.seimei, self.vision)
        self.assertIsNotNone(result)
        parsed = VisionObservation(**result)
        self.assertEqual(parsed.page, 'story_dialogue_wait')
        self.assertIn('recorded_camera_calibration:xiaobai_reentry', parsed.evidence)
        for name in AREAS:
            self.assertIsNone(getattr(parsed, name))
        self.assertIsNone(parsed.identity)
        self.assertIsNone(parsed.level)

    def test_every_name_widget_and_scene_anchor_is_required_for_skip(self):
        for name, area in {**self.widgets, **SCENES[VARIANT]}.items():
            with self.subTest(missing=name):
                frame = self.xiaobai.copy()
                replace_area(frame, area, 0)
                self.assertIsNone(self.observe(frame))
                wait = observe_dialogue_wait(frame, self.vision)
                if name == 'speaker':
                    self.assertIsNotNone(wait)
                    for field in AREAS:
                        self.assertIsNone(wait[field])
                else:
                    self.assertIsNone(wait)

    def test_black_dimming_and_anchor_overlays_reject_actions_and_wait(self):
        for original in (self.xiaobai, self.seimei):
            for factor in (0.0, 0.5, 0.8, 0.95, 1.10):
                frame = np.clip(original.astype(float) * factor, 0, 255).astype(np.uint8)
                self.assertIsNone(self.observe(frame))
                self.assertIsNone(observe_dialogue_wait(frame, self.vision))
            # Covers the stated anchor-intersecting modal negatives, not every
            # arbitrary overlay hidden entirely among the animated characters.
            for area in ((500, 70, 400, 380), (320, 540, 650, 165),
                         (100, 80, 240, 250)):
                for opacity in (0.4, 1.0):
                    frame = original.copy()
                    x, y, width, height = area
                    old = frame[y:y + height, x:x + width].astype(float)
                    replace_area(frame, area, (old * (1 - opacity)
                                 + np.array((220, 200, 165)) * opacity).astype(np.uint8))
                    self.assertIsNone(self.observe(frame))
                    self.assertIsNone(observe_dialogue_wait(frame, self.vision))

    def test_widgets_pasted_on_black_courtyard_or_old_camera_are_rejected(self):
        for background in (np.zeros_like(self.xiaobai), read_frame('courtyard_1280.png'),
                           read_frame('story_dialogue_1280.png')):
            frame = background.copy()
            for area in self.widgets.values():
                x, y, width, height = area
                replace_area(frame, area, self.xiaobai[y:y + height, x:x + width])
            self.assertIsNone(self.observe(frame))
            self.assertIsNone(observe_dialogue_wait(frame, self.vision))

    def test_synthetic_changed_portrait_and_dialogue_body_are_not_pose_templates(self):
        frame = self.xiaobai.copy()
        replace_area(frame, (935, 495, 345, 225), (25, 40, 70))
        replace_area(frame, (340, 615, 570, 31), (30, 25, 20))
        self.assertIsNotNone(self.observe(frame))


if __name__ == '__main__':
    unittest.main()
