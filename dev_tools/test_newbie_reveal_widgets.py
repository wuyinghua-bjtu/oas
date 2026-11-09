"""Offline tests of reusable reveal controls; no device access."""
from pathlib import Path
import unittest

import cv2
import numpy as np

from tasks.NewbieLeveling.reveal_widgets import observe_reveal_widgets
from tasks.NewbieLeveling.vision import NewbieVision


FIXTURES = Path(__file__).with_name("fixtures") / "newbie_leveling"


def frame(name):
    image = cv2.imdecode(np.fromfile(str(FIXTURES / name), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise AssertionError("Missing fixture " + name)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


class RevealWidgetTests(unittest.TestCase):
    def setUp(self):
        self.vision = NewbieVision()

    def observe(self, image):
        return observe_reveal_widgets(image, self.vision)

    def test_all_thirteen_original_camera1_frames(self):
        sources = ["story_reveal_1280.png"]
        for folder in ("story_reveal_motion", "story_reveal_heldout"):
            sources += [folder + "/" + p.name for p in sorted((FIXTURES / folder).glob("*.png"))]
        self.assertEqual(len(sources), 13)
        for name in sources:
            result = self.observe(frame(name))
            self.assertEqual(result["page"], "story_reveal", (name, result))
            self.assertEqual(result["npc_story_area"], (891, 282, 16, 26))

    def test_all_six_camera1_ghost_frames_after_courtyard_reentry(self):
        paths = sorted((FIXTURES / "reveal_widget_camera1_ghost").glob("*.png"))
        self.assertEqual(len(paths), 6)
        for path in paths:
            name = "reveal_widget_camera1_ghost/" + path.name
            with self.subTest(frame=name):
                result = self.observe(frame(name))
                self.assertEqual(result["page"], "story_reveal", (name, result))
                # Same camera, different quest NPC: these are original live
                # captures, not edits moving the old cat target in its frame.
                self.assertEqual(result["npc_story_area"], (781, 278, 16, 26))
                self.assertEqual(result["return_area"], (29, 29, 24, 24))
                self.assertIn("camera1", result["evidence"])

    def test_six_camera3_frames_and_later_stable_holdouts(self):
        sources = []
        for folder, count in (("reveal_widget_camera3", 6), ("reveal_widget_heldout", 3)):
            paths = sorted((FIXTURES / folder).glob("*.png"))
            self.assertEqual(len(paths), count)
            sources += [folder + "/" + p.name for p in paths]
        for name in sources:
            result = self.observe(frame(name))
            if name == "reveal_widget_heldout/1788879978001865400-00.png":
                # This real animation frame exceeds the unchanged glyph
                # absolute-error limit (10.594 > 10); reject it rather than
                # widening the threshold to fit one noisy frame. Both next
                # independently captured frames below pass consecutively.
                self.assertEqual(result["page"], "unknown")
                self.assertIsNone(result["npc_story_area"])
                continue
            self.assertEqual(result["page"], "story_reveal", (name, result))
            self.assertEqual(result["npc_story_area"], (580, 278, 16, 26))
            self.assertEqual(result["return_area"], (29, 29, 24, 24))

    def test_matching_scene_without_question_is_authoritative_unknown(self):
        image = frame("reveal_widget_camera3_1280.png")
        image[260:325, 559:618] = 0
        result = self.observe(image)
        self.assertIsNotNone(result)
        self.assertEqual(result["page"], "unknown")
        self.assertIsNone(result["npc_story_area"])

    def test_duplicate_questions_are_authoritative_ambiguous(self):
        for name, roi in (("story_reveal_1280.png", (870, 264)),
                           ("reveal_widget_camera3_1280.png", (559, 260))):
            image = frame(name)
            x, y = roi
            image[264:329, 480:539] = image[y:y+65, x:x+59]
            result = self.observe(image)
            self.assertEqual(result["page"], "unknown", result)
            self.assertEqual(result["reason"], "reveal_widget_question_ambiguous")

    def test_camera1_ghost_duplicate_outside_action_band_still_blocks_input(self):
        image = frame("reveal_widget_camera1_ghost/1788880590417369000-00.png")
        # The second target is x=251, outside the authorized click band but
        # inside the larger recognition band. Uniqueness must be checked FIRST.
        image[264:329, 230:289] = image[260:325, 760:819]
        result = self.observe(image)
        self.assertEqual(result["page"], "unknown", result)
        self.assertIsNone(result["npc_story_area"])
        self.assertEqual(result["reason"], "reveal_widget_question_ambiguous")

    def test_camera1_question_outside_verified_central_npc_band_is_rejected(self):
        image = frame("story_reveal_1280.png")
        image[264:329, 230:289] = image[264:329, 870:929]
        image[264:329, 870:929] = 0
        result = self.observe(image)
        self.assertEqual(result["page"], "unknown")
        self.assertEqual(result["reason"], "reveal_widget_camera1_target_unverified")

    def test_camera3_widget_can_move_within_npc_band(self):
        image = frame("reveal_widget_camera3_1280.png")
        image[264:329, 480:539] = image[260:325, 559:618]
        image[260:325, 559:618] = 0
        result = self.observe(image)
        self.assertEqual(result["page"], "story_reveal", result)
        self.assertEqual(result["npc_story_area"], (501, 282, 16, 26))

    def test_glyph_without_ring_does_not_authorize_click(self):
        image = frame("reveal_widget_camera3_1280.png")
        glyph = image[274:308, 578:599].copy()
        image[260:325, 559:618] = 0
        image[274:308, 578:599] = glyph
        self.assertEqual(self.observe(image)["page"], "unknown")

    def test_camera3_dimming_modal_return_and_static_anchor_failures(self):
        source = frame("reveal_widget_camera3_1280.png")
        self.assertNotEqual((self.observe((source.astype(float) * .55).astype(np.uint8)) or {}) .get("page"), "story_reveal")
        for x, y, w, h in ((995, 96, 174, 94), (28, 80, 145, 120),
                           (320, 590, 720, 110), (338, 160, 105, 70),
                           (15, 15, 54, 55), (440, 250, 580, 330)):
            image = source.copy()
            image[y:y+h, x:x+w] = (220, 210, 180)
            result = self.observe(image)
            self.assertIsNotNone(result)
            self.assertEqual(result["page"], "unknown", (x, y, result))

    def test_unrelated_or_black_screen_is_not_a_scene(self):
        for image in (np.zeros((720, 1280, 3), np.uint8), frame("courtyard_1280.png"),
                      frame("story_eye_reentry_1280.png")):
            self.assertNotEqual((self.observe(image) or {}).get("page"), "story_reveal")


if __name__ == "__main__":
    unittest.main()
