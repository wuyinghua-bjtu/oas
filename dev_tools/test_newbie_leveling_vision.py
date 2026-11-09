"""Offline starter-courtyard regression tests; never imports a device driver.

Run with toolkit/python.exe -m unittest dev_tools.test_newbie_leveling_vision.
Add NEWBIE_VISION_REAL_OCR=1 to exercise the installed local OCR as well.
"""
import os
from pathlib import Path
import unittest

import cv2
import numpy as np

from tasks.NewbieLeveling.vision import (
    IDENTITY_ROI, LEVEL_ROI, NPC_SEARCH_ROI, NewbieVision, normalize_frame,
)


FIXTURES = Path(__file__).with_name("fixtures") / "newbie_leveling"
CAPTURES = ("courtyard_1050.png", "courtyard_moved_1050.png", "courtyard_1280.png")


def read_frame(name):
    frame = cv2.imdecode(np.fromfile(str(FIXTURES / name), dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise AssertionError("Missing real screenshot fixture: " + name)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def fake_reader(crop, field):
    return "test_account" if field == "identity" else "3"


class NewbieVisionTests(unittest.TestCase):
    def setUp(self):
        self.vision = NewbieVision(text_reader=fake_reader)
        self.frame = normalize_frame(read_frame("courtyard_1280.png"))

    def test_three_real_courtyard_captures_and_npc_movement(self):
        expected = ((846, 247), (729, 247), (846, 247))
        for filename, (x, y) in zip(CAPTURES, expected):
            with self.subTest(filename=filename):
                observation = self.vision.observe(read_frame(filename))
                self.assertEqual(observation.page, "courtyard")
                self.assertEqual(observation.level, 3)
                self.assertEqual(observation.identity, "test_account")
                self.assertEqual(observation.npc_story_area, (x, y, 20, 18))
                self.assertEqual(observation.reason, "verified_story_npc")

    def test_normalize_aspect_ratio_size_and_dtype(self):
        self.assertEqual(normalize_frame(read_frame(CAPTURES[0])).shape, (720, 1280, 3))
        for bad in (np.zeros((720, 1280), np.uint8),
                    np.zeros((720, 1000, 3), np.uint8),
                    np.zeros((180, 320, 3), np.uint8),
                    np.zeros((720, 1280, 3), np.float32), None):
            with self.subTest(shape=getattr(bad, "shape", None)):
                self.assertEqual(self.vision.observe(bad).page, "unknown")

    def test_blank_noise_and_unrecognized_pages_never_read_ocr(self):
        calls = []
        def forbidden_reader(*args):
            calls.append(args[1])
            return "3"
        vision = NewbieVision(text_reader=forbidden_reader)
        for frame in (np.zeros_like(self.frame), np.full_like(self.frame, 255),
                      np.random.default_rng(1).integers(0, 256, self.frame.shape, dtype=np.uint8)):
            result = vision.observe(frame)
            self.assertEqual(result.page, "unknown")
            self.assertIsNone(result.npc_story_area)
            self.assertIsNone(result.level)
        self.assertEqual(calls, [], "OCR must not run before independent courtyard anchors")

    def test_each_independent_anchor_is_required(self):
        for roi in ((350, 20, 53, 69), (312, 30, 34, 59), (49, 98, 1033, 61)):
            frame = self.frame.copy()
            x, y, w, h = roi
            frame[y:y+h, x:x+w] = 0
            self.assertEqual(self.vision.observe(frame).page, "unknown")

    def test_dimmed_dialog_background_is_rejected(self):
        dimmed = (self.frame.astype(float) * 0.55).astype(np.uint8)
        observation = self.vision.observe(dimmed)
        self.assertEqual(observation.page, "unknown")
        self.assertIsNone(observation.npc_story_area)

    def test_popup_covering_npc_has_no_generic_confirm_action(self):
        frame = self.frame.copy()
        cv2.rectangle(frame, (360, 180), (1050, 560), (226, 205, 153), -1)
        cv2.rectangle(frame, (730, 480), (900, 540), (180, 90, 30), -1)
        observation = self.vision.observe(frame)
        self.assertIsNone(observation.npc_story_area)

    def test_summon_lantern_and_out_of_roi_bubble_are_not_story_actions(self):
        frame = self.frame.copy()
        # Preserve the actual summon lantern, replace only the story NPC bubble.
        frame[227:289, 826:887] = (15, 30, 70)
        # An exact copied bubble outside the verified NPC region is still ignored.
        frame[400:462, 1050:1111] = self.frame[227:289, 826:887]
        observation = self.vision.observe(frame)
        self.assertEqual(observation.page, "courtyard")
        self.assertIsNone(observation.npc_story_area)

    def test_ring_without_dots_and_dots_without_ring_are_not_actions(self):
        ring_only = self.frame.copy()
        ring_only[247:266, 836:877] = (35, 22, 43)
        self.assertIsNone(self.vision.observe(ring_only).npc_story_area)
        dots_only = self.frame.copy()
        dots_only[227:289, 826:887] = (35, 22, 43)
        for x in (844, 857, 870):
            cv2.circle(dots_only, (x, 258), 3, (230, 210, 210), -1)
        self.assertIsNone(self.vision.observe(dots_only).npc_story_area)

    def test_level_reader_is_exact_badge_crop_not_resource_time_or_shikigami(self):
        observed = []
        def reader(crop, field):
            observed.append((crop.shape, field))
            return fake_reader(crop, field)
        NewbieVision(text_reader=reader).observe(self.frame)
        self.assertEqual(observed, [((23, 26, 3), "level_100"),
                                    ((23, 26, 3), "level_140"),
                                    ((30, 190, 3), "identity")])
        frame = self.frame.copy()
        x, y, w, h = LEVEL_ROI
        frame[y:y+h, x:x+w] = 0
        cv2.putText(frame, "30", (500, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        result = self.vision.observe(frame)
        self.assertIsNone(result.level)
        self.assertIsNone(result.npc_story_area)

    def test_bad_or_disagreeing_level_readings_fail_closed(self):
        for value in ("", "0", "99", "61", "03", "3:00", "S", "3级", "_3", None):
            vision = NewbieVision(text_reader=lambda crop, field: "account" if field == "identity" else value)
            result = vision.observe(self.frame)
            self.assertIsNone(result.level)
            self.assertIsNone(result.npc_story_area)
        vision = NewbieVision(text_reader=lambda crop, field: {
            "identity": "account", "level_100": "3", "level_140": "30"}[field])
        self.assertIsNone(vision.observe(self.frame).level)

    def test_target_level_is_not_truncated_by_parser(self):
        vision = NewbieVision(text_reader=lambda crop, field: "account" if field == "identity" else "30")
        self.assertEqual(vision.observe(self.frame).level, 30)

    def test_no_account_identity_means_no_click_suggestion(self):
        vision = NewbieVision(text_reader=lambda crop, field: "" if field == "identity" else "3")
        result = vision.observe(self.frame)
        self.assertIsNone(result.identity)
        self.assertIsNone(result.npc_story_area)

    def test_ocr_exception_means_unknown_not_a_fallback_click(self):
        def failed_reader(*args):
            raise RuntimeError("offline OCR unavailable")
        result = NewbieVision(text_reader=failed_reader).observe(self.frame)
        self.assertEqual(result.page, "unknown")
        self.assertEqual(result.reason, "vision_error:RuntimeError")

    def test_real_tree_scene_has_bounded_npc_and_return_without_account_ocr(self):
        calls = []
        def reader(crop, field):
            calls.append(field)
            return "3"
        result = NewbieVision(text_reader=reader).observe(read_frame("story_scene_1280.png"))
        self.assertEqual(result.page, "story_scene")
        self.assertEqual(result.npc_story_area, (189, 261, 20, 18))
        self.assertEqual(result.return_area, (29, 29, 24, 24))
        self.assertIsNone(result.level)
        self.assertIsNone(result.identity)
        self.assertEqual(calls, [])
        self.assertIn("story_layout_clear", result.evidence)

    def test_story_scene_requires_both_decorations_and_back(self):
        for roi in ((660, 130, 110, 95), (1096, 97, 149, 101),
                    (15, 15, 54, 55)):
            with self.subTest(roi=roi):
                frame = read_frame("story_scene_1280.png")
                x, y, w, h = roi
                frame[y:y+h, x:x+w] = 0
                result = self.vision.observe(frame)
                self.assertEqual(result.page, "unknown")
                self.assertIsNone(result.npc_story_area)
                self.assertIsNone(result.return_area)

    def test_story_scene_rejects_dimmed_backgrounds(self):
        for factor in (0.55, 0.85, 0.95):
            frame = (read_frame("story_scene_1280.png").astype(float) * factor).astype(np.uint8)
            self.assertEqual(self.vision.observe(frame).page, "unknown", factor)

    def test_story_scene_rejects_dialogue_and_modal_occlusion_across_layout(self):
        # Include overlays away from both small decoration anchors and the back
        # button: those must be caught by the independent whole-layout guard.
        for roi in ((400, 230, 480, 260), (0, 540, 1280, 180),
                    (80, 350, 280, 260), (940, 220, 330, 310),
                    (200, 0, 650, 100), (380, 420, 450, 70)):
            with self.subTest(roi=roi):
                frame = read_frame("story_scene_1280.png")
                x, y, w, h = roi
                frame[y:y+h, x:x+w] = (226, 205, 153)
                result = self.vision.observe(frame)
                self.assertEqual(result.page, "unknown")
                self.assertIsNone(result.return_area)

    def test_story_scene_rejects_semtransparent_center_modal(self):
        frame = read_frame("story_scene_1280.png")
        overlay = np.full_like(frame[350:650, 350:850], (230, 230, 230))
        frame[350:650, 350:850] = cv2.addWeighted(frame[350:650, 350:850], .65, overlay, .35, 0)
        self.assertEqual(self.vision.observe(frame).page, "unknown")

    def test_courtyard_never_offers_story_scene_return_button(self):
        for filename in CAPTURES:
            result = self.vision.observe(read_frame(filename))
            self.assertEqual(result.page, "courtyard")
            self.assertIsNone(result.return_area)

    def test_story_back_icon_and_bubble_pasted_on_unknown_page_do_not_enable_clicks(self):
        source = read_frame("story_scene_1280.png")
        frame = np.zeros_like(source)
        for x, y, w, h in ((15, 15, 54, 55), (169, 241, 59, 60)):
            frame[y:y+h, x:x+w] = source[y:y+h, x:x+w]
        result = self.vision.observe(frame)
        self.assertEqual(result.page, "unknown")
        self.assertIsNone(result.return_area)
        self.assertIsNone(result.npc_story_area)

    def test_scene_bubble_outside_verified_left_roi_is_not_actionable(self):
        frame = read_frame("story_scene_1280.png")
        frame[241:301, 900:959] = frame[241:301, 169:228]
        frame[241:301, 169:228] = (50, 60, 40)
        result = self.vision.observe(frame)
        self.assertIsNone(result.npc_story_area)

    def test_story_scene_return_remains_verified_when_npc_bubble_is_missing(self):
        frame = read_frame("story_scene_1280.png")
        frame[241:301, 169:228] = (50, 60, 40)
        result = self.vision.observe(frame)
        self.assertEqual(result.page, "story_scene")
        self.assertEqual(result.return_area, (29, 29, 24, 24))
        self.assertIsNone(result.npc_story_area)
        self.assertEqual(result.reason, "story_npc_unstable")
        self.assertIsNone(result.level)
        self.assertIsNone(result.identity)

    def test_all_twelve_real_motion_frames_stably_identify_scene(self):
        paths = sorted((FIXTURES / "story_scene_motion").glob("*.png"))
        self.assertEqual(len(paths), 12)
        for path in paths:
            with self.subTest(frame=path.name):
                # Six odd frames were not used to build the motion bounds.
                result = self.vision.observe(read_frame("story_scene_motion/" + path.name))
                self.assertEqual(result.page, "story_scene", result)
                self.assertEqual(result.return_area, (29, 29, 24, 24))
                self.assertEqual(result.npc_story_area, (189, 261, 20, 18))

    def test_real_motion_frames_still_reject_modals_and_dimming(self):
        paths = sorted((FIXTURES / "story_scene_motion").glob("*.png"))
        for path in paths:
            frame = read_frame("story_scene_motion/" + path.name)
            modal = frame.copy()
            modal[350:650, 350:850] = (220, 210, 180)
            self.assertEqual(self.vision.observe(modal).page, "unknown", path.name)
            dimmed = (frame.astype(float) * 0.95).astype(np.uint8)
            self.assertEqual(self.vision.observe(dimmed).page, "unknown", path.name)

    def test_layout_failure_has_specific_unknown_reason(self):
        frame = read_frame("story_scene_1280.png")
        frame[350:650, 350:850] = (220, 210, 180)
        result = self.vision.observe(frame)
        self.assertEqual(result.page, "unknown")
        self.assertEqual(result.reason, "story_layout_changed")

    def test_scene_camera_layout_change_fails_closed(self):
        frame = np.roll(read_frame("story_scene_1280.png"), 40, axis=1)
        self.assertEqual(self.vision.observe(frame).page, "unknown")

    def test_real_xiaobai_dialogue_has_explicit_skip_and_no_account_read(self):
        calls = []
        vision = NewbieVision(text_reader=lambda crop, field: calls.append(field))
        result = vision.observe(read_frame("story_dialogue_1280.png"))
        self.assertEqual(result.page, "story_dialogue")
        self.assertEqual(result.story_skip_area, (846, 564, 48, 20))
        self.assertEqual(result.return_area, (29, 29, 24, 24))
        self.assertIsNone(result.tutorial_area)
        self.assertIsNone(result.npc_story_area)
        self.assertIsNone(result.level)
        self.assertIsNone(result.identity)
        self.assertEqual(calls, [])

    def test_eight_real_eye_frames_including_four_held_out(self):
        paths = sorted((FIXTURES / "story_eye_motion").glob("*.png"))
        self.assertEqual(len(paths), 8)
        for path in paths:
            with self.subTest(frame=path.name):
                result = self.vision.observe(read_frame("story_eye_motion/" + path.name))
                self.assertEqual(result.page, "story_eye", result)
                self.assertEqual(result.tutorial_area, (618, 140, 44, 34))
                self.assertEqual(result.return_area, (29, 29, 24, 24))
                self.assertIsNone(result.story_skip_area)
                self.assertIsNone(result.npc_story_area)
                self.assertIsNone(result.level)
                self.assertIsNone(result.identity)

    def test_dialogue_actions_require_scene_return_panel_speaker_and_skip(self):
        for x, y, w, h in ((751, 131, 98, 111), (1190, 92, 90, 111),
                           (15, 15, 54, 55), (826, 554, 91, 40),
                           (345, 558, 67, 35), (10, 634, 220, 76)):
            frame = read_frame("story_dialogue_1280.png")
            frame[y:y+h, x:x+w] = 0
            result = self.vision.observe(frame)
            expected = "story_dialogue_wait" if (x, y, w, h) == (345, 558, 67, 35) else "unknown"
            self.assertEqual(result.page, expected)
            self.assertIsNone(result.story_skip_area)
            self.assertIsNone(result.tutorial_area)
            self.assertIsNone(result.return_area)
            self.assertIsNone(result.npc_story_area)

    def test_eye_requires_static_scene_return_and_eye_symbol(self):
        source = sorted((FIXTURES / "story_eye_motion").glob("*.png"))[0]
        for x, y, w, h in ((751, 131, 98, 111), (1190, 92, 90, 111),
                           (15, 15, 54, 55), (574, 89, 132, 134)):
            frame = read_frame("story_eye_motion/" + source.name)
            frame[y:y+h, x:x+w] = 0
            result = self.vision.observe(frame)
            self.assertEqual(result.page, "unknown")
            self.assertIsNone(result.tutorial_area)

    def test_dialogue_and_eye_reject_purchase_account_and_other_modals(self):
        sources = ["story_dialogue_1280.png"] + [
            "story_eye_motion/" + p.name for p in sorted((FIXTURES / "story_eye_motion").glob("*.png"))]
        for name in sources:
            for roi in ((350, 280, 580, 280), (500, 370, 340, 240),
                        (0, 570, 1280, 150), (200, 90, 240, 270)):
                frame = read_frame(name)
                x, y, w, h = roi
                frame[y:y+h, x:x+w] = (222, 208, 180)
                cv2.putText(frame, "BUY / LOGIN", (x + 10, y + 40),
                            cv2.FONT_HERSHEY_SIMPLEX, .8, (40, 20, 10), 2)
                result = self.vision.observe(frame)
                self.assertEqual(result.page, "unknown", (name, roi, result))
                self.assertIsNone(result.story_skip_area)
                self.assertIsNone(result.tutorial_area)

    def test_dialogue_and_eye_dimming_never_leave_actions(self):
        sources = ["story_dialogue_1280.png"] + [
            "story_eye_motion/" + p.name for p in sorted((FIXTURES / "story_eye_motion").glob("*.png"))]
        for name in sources:
            frame = (read_frame(name).astype(float) * 0.95).astype(np.uint8)
            result = self.vision.observe(frame)
            self.assertEqual(result.page, "unknown", name)
            self.assertIsNone(result.return_area)
            self.assertIsNone(result.story_skip_area)
            self.assertIsNone(result.tutorial_area)

    def test_eye_with_dialogue_footer_is_not_a_tutorial_click(self):
        source = sorted((FIXTURES / "story_eye_motion").glob("*.png"))[0]
        frame = read_frame("story_eye_motion/" + source.name)
        frame[490:720] = read_frame("story_dialogue_1280.png")[490:720]
        result = self.vision.observe(frame)
        # Recognized dialogue chrome can only authorize passive waiting;
        # mixing it with an eye tutorial must never yield any input target.
        self.assertEqual(result.page, "story_dialogue_wait")
        self.assertIsNone(result.tutorial_area)
        self.assertIsNone(result.story_skip_area)
        self.assertIsNone(result.return_area)
        self.assertIsNone(result.npc_story_area)

    def test_icons_pasted_on_wrong_scene_do_not_enable_new_action_types(self):
        source = sorted((FIXTURES / "story_eye_motion").glob("*.png"))[0]
        eye = read_frame("story_eye_motion/" + source.name)
        dialogue = read_frame("story_dialogue_1280.png")
        for name in ("courtyard_1280.png", "story_scene_1280.png"):
            frame = read_frame(name)
            frame[89:223, 574:706] = eye[89:223, 574:706]
            frame[554:594, 826:917] = dialogue[554:594, 826:917]
            result = self.vision.observe(frame)
            self.assertNotIn(result.page, ("story_eye", "story_dialogue"))
            self.assertIsNone(result.tutorial_area)
            self.assertIsNone(result.story_skip_area)

    def test_dialogue_synthetic_motion_transfer_from_held_out_eye_frames(self):
        # Only one real dialogue capture is available. These are explicitly
        # synthetic composites, transferring recorded foreground idle motion;
        # they are not claimed as extra real dialogue screenshots.
        for path in sorted((FIXTURES / "story_eye_motion").glob("*.png"))[1::2]:
            frame = read_frame("story_dialogue_1280.png")
            eye = read_frame("story_eye_motion/" + path.name)
            for x, y, w, h in ((335, 230, 425, 315), (1190, 270, 90, 260)):
                frame[y:y+h, x:x+w] = eye[y:y+h, x:x+w]
            result = self.vision.observe(frame)
            self.assertEqual(result.page, "story_dialogue", (path.name, result))
            self.assertIsNotNone(result.story_skip_area)

    def test_eye_reentry_camera1_real_capture_and_eight_motion_frames(self):
        paths = sorted((FIXTURES / "story_eye_reentry_motion").glob("*.png"))
        self.assertEqual(len(paths), 8)
        sources = ["story_eye_reentry_1280.png"] + ["story_eye_reentry_motion/" + p.name for p in paths]
        for name in sources:
            with self.subTest(frame=name):
                result = self.vision.observe(read_frame(name))
                self.assertEqual(result.page, "story_eye", result)
                self.assertEqual(result.tutorial_area, (618, 140, 44, 34))
                self.assertEqual(result.return_area, (29, 29, 24, 24))
                self.assertIn("camera1_tree_paper", result.evidence)
                self.assertIsNone(result.level)
                self.assertIsNone(result.identity)

    def test_eye_two_observed_cameras_have_separate_environment_evidence(self):
        old_camera = sorted((FIXTURES / "story_eye_motion").glob("*.png"))[0]
        scene2 = self.vision.observe(read_frame("story_eye_motion/" + old_camera.name))
        scene1 = self.vision.observe(read_frame("story_eye_reentry_1280.png"))
        self.assertIn("story2_tree", scene2.evidence)
        self.assertIn("camera1_tree_paper", scene1.evidence)
        self.assertNotIn("camera1_tree_paper", scene2.evidence)
        self.assertEqual(scene1.tutorial_area, scene2.tutorial_area)

    def test_eye_reentry_requires_unobscured_environment_back_and_eye(self):
        for x, y, w, h in ((760, 305, 128, 85), (1096, 97, 149, 101),
                           (15, 15, 54, 55), (574, 89, 132, 134)):
            frame = read_frame("story_eye_reentry_1280.png")
            frame[y:y+h, x:x+w] = 0
            result = self.vision.observe(frame)
            self.assertEqual(result.page, "unknown", result)
            self.assertIsNone(result.tutorial_area)

    def test_character_motion_bounds_are_not_ignored_modal_regions(self):
        # These panels lie wholly inside declared foreground rectangles. They
        # must still fail measured pixel bounds, even though animation is legal.
        for roi in ((125, 395, 130, 165), (545, 350, 155, 155),
                    (1070, 325, 150, 160), (355, 370, 140, 110)):
            frame = read_frame("story_eye_reentry_1280.png")
            x, y, w, h = roi
            frame[y:y+h, x:x+w] = (230, 220, 190)
            result = self.vision.observe(frame)
            self.assertEqual(result.page, "unknown", (roi, result))
            self.assertIsNone(result.return_area)

    def test_eye_reentry_all_frames_reject_dimming_dialogue_and_purchase_panels(self):
        for path in sorted((FIXTURES / "story_eye_reentry_motion").glob("*.png")):
            frame = read_frame("story_eye_reentry_motion/" + path.name)
            dimmed = (frame.astype(float) * .95).astype(np.uint8)
            self.assertEqual(self.vision.observe(dimmed).page, "unknown", path.name)
            modal = frame.copy()
            modal[330:630, 380:890] = (220, 210, 180)
            self.assertEqual(self.vision.observe(modal).page, "unknown", path.name)
            footer = frame.copy()
            footer[570:720] = read_frame("story_dialogue_1280.png")[570:720]
            self.assertEqual(self.vision.observe(footer).page, "unknown", path.name)

    def test_eye_reentry_unobserved_camera_shift_remains_unknown(self):
        frame = np.roll(read_frame("story_eye_reentry_1280.png"), 35, axis=1)
        result = self.vision.observe(frame)
        self.assertEqual(result.page, "unknown")
        self.assertIsNone(result.tutorial_area)

    def test_reveal_real_pause_eight_motion_and_four_late_heldout_frames(self):
        motion = sorted((FIXTURES / "story_reveal_motion").glob("*.png"))
        heldout = sorted((FIXTURES / "story_reveal_heldout").glob("*.png"))
        self.assertEqual((len(motion), len(heldout)), (8, 4))
        sources = ["story_reveal_1280.png"] + ["story_reveal_motion/" + p.name for p in motion]
        sources += ["story_reveal_heldout/" + p.name for p in heldout]
        for name in sources:
            result = self.vision.observe(read_frame(name))
            self.assertEqual(result.page, "story_reveal", (name, result))
            self.assertEqual(result.npc_story_area, (891, 282, 16, 26))
            self.assertEqual(result.return_area, (29, 29, 24, 24))
            self.assertIsNone(result.level)
            self.assertIsNone(result.identity)
            self.assertIsNone(result.tutorial_area)
            self.assertIsNone(result.story_skip_area)

    def test_reveal_requires_dark_background_bright_characters_question_and_return(self):
        for roi in ((1096, 97, 149, 101), (115, 78, 130, 125), (320, 590, 720, 110),
                    (455, 156, 110, 76), (15, 15, 54, 55), (870, 264, 59, 65),
                    (120, 390, 115, 120), (585, 295, 110, 125), (1060, 280, 125, 140)):
            frame = read_frame("story_reveal_1280.png")
            x, y, w, h = roi
            frame[y:y+h, x:x+w] = 0
            result = self.vision.observe(frame)
            self.assertEqual(result.page, "unknown", (roi, result))
            self.assertIsNone(result.npc_story_area)
            self.assertIsNone(result.return_area)

    def test_reveal_is_not_black_screen_or_globally_darkened_normal_scene(self):
        reveal = read_frame("story_reveal_1280.png")
        black = np.zeros_like(reveal)
        black[15:70, 15:69] = reveal[15:70, 15:69]
        black[264:329, 870:929] = reveal[264:329, 870:929]
        self.assertEqual(self.vision.observe(black).page, "unknown")
        for factor in (.2, .35, .55):
            frame = (read_frame("story_scene_1280.png").astype(float) * factor).astype(np.uint8)
            frame[264:329, 870:929] = reveal[264:329, 870:929]
            self.assertEqual(self.vision.observe(frame).page, "unknown", factor)

    def test_reveal_further_dimming_and_obvious_modal_overlays_fail_closed(self):
        frame = read_frame("story_reveal_1280.png")
        for factor in (.55, .85, .95):
            dimmed = (frame.astype(float) * factor).astype(np.uint8)
            self.assertEqual(self.vision.observe(dimmed).page, "unknown", factor)
        for roi in ((350, 250, 580, 320), (0, 570, 1280, 150), (740, 230, 270, 270)):
            modal = frame.copy()
            x, y, w, h = roi
            modal[y:y+h, x:x+w] = (225, 215, 180)
            self.assertEqual(self.vision.observe(modal).page, "unknown", roi)

    def test_reveal_question_outside_observed_npc_position_is_not_clickable(self):
        frame = read_frame("story_reveal_1280.png")
        frame[264:329, 230:289] = frame[264:329, 870:929]
        frame[264:329, 870:929] = 0
        self.assertIsNone(self.vision.observe(frame).npc_story_area)

    @unittest.skipUnless(os.getenv("NEWBIE_VISION_REAL_OCR") == "1", "opt-in installed local OCR regression")
    def test_real_ruleocr_on_all_verified_captures(self):
        vision = NewbieVision()
        identities = []
        for filename in CAPTURES:
            result = vision.observe(read_frame(filename))
            self.assertEqual(result.level, 3, (filename, result))
            self.assertIsNotNone(result.identity)
            self.assertIsNotNone(result.npc_story_area)
            identities.append(result.identity)
        self.assertEqual(len(set(identities)), 1)


if __name__ == "__main__":
    unittest.main()
