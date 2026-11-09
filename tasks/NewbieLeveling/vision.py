"""Conservative, local-only observations for verified starter screens.

Images use OAS's RGB convention. Coordinates are (x, y, width, height) at
1280x720. This module never connects to a device and never clicks anything.
Unknown tutorials/dialogs deliberately have no action. A caller must also
require stable consecutive observations and its account/target-level guards.
"""
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Optional, Tuple

import cv2
import numpy as np


Area = Tuple[int, int, int, int]
ASSETS = Path(__file__).with_name("vision_assets")
ROOT = Path(__file__).resolve().parents[2]
LEVEL_ROI: Area = (6, 22, 26, 23)
IDENTITY_ROI: Area = (129, 28, 190, 30)
# Measured NPC positions in the two 2026-09-08 courtyard captures. Do not
# expand this into a whole-screen search: summon lanterns are not story NPCs.
NPC_SEARCH_ROI: Area = (660, 210, 290, 105)
STORY_NPC_SEARCH_ROI: Area = (159, 231, 79, 80)
# Independently recorded after closing the eye: Tanuki's dialogue bubble.
STORY_TANUKI_SEARCH_ROI: Area = (1080, 195, 80, 85)
# Camera 1 foreground occupancy observed before/after courtyard re-entry.
# Bounds permit measured pixel changes only within these rectangles; these
# regions are NOT discarded from the overlay/occlusion comparison.
CAMERA1_CHARACTER_ROIS: Tuple[Area, ...] = (
    (90, 325, 200, 325), (330, 340, 210, 170),
    (485, 225, 255, 360), (1025, 265, 250, 280),
)


@dataclass(frozen=True)
class VisionObservation:
    page: str = "unknown"
    level: Optional[int] = None
    identity: Optional[str] = None
    npc_story_area: Optional[Area] = None
    evidence: Tuple[str, ...] = ()
    reason: str = "unrecognized_screen"
    return_area: Optional[Area] = None
    story_skip_area: Optional[Area] = None
    tutorial_area: Optional[Area] = None


def normalize_frame(image: np.ndarray) -> np.ndarray:
    """Normalize only game-content frames; reject odd aspect ratios/blank input."""
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected an RGB game-content frame")
    height, width = image.shape[:2]
    if image.dtype != np.uint8 or width < 640 or height < 360:
        raise ValueError("Frame must be uint8 and at least 640x360")
    if abs(width / height - 16 / 9) > 0.015:
        raise ValueError("Frame is not a verified 16:9 game-content image")
    if (width, height) == (1280, 720):
        return image
    return cv2.resize(image, (1280, 720), interpolation=cv2.INTER_LINEAR)


def _crop(image: np.ndarray, area: Area) -> np.ndarray:
    x, y, width, height = area
    return image[y:y + height, x:x + width]


class NewbieVision:
    """Recognize only independently anchored, currently verified game screens.

    text_reader is a test seam accepting (RGB crop, field). Production uses
    RuleOcr in Single mode, without permissive Digit substitutions or numeric
    rescue. OCR failures return None rather than a guessed level or identity.
    """

    def __init__(self, text_reader: Optional[Callable] = None):
        self._text_reader = text_reader
        self._rules = {}
        self._templates = {}

    def _read(self, crop: np.ndarray, field: str) -> str:
        if self._text_reader is not None:
            return self._text_reader(crop, field)
        # Lazy import keeps offline detector tests independent of OCR runtime.
        from module.atom.ocr import RuleOcr
        if field not in self._rules:
            h, w = crop.shape[:2]
            rule = RuleOcr(name="newbie_" + field, mode="Single", method="Default",
                           roi=(0, 0, w, h), area=(0, 0, w, h), keyword="")
            rule.score = 0.90
            rule.min_score = 0.90
            self._rules[field] = rule
        return self._rules[field].ocr_single_line(crop)

    def _template(self, path: Path) -> np.ndarray:
        key = str(path)
        if key not in self._templates:
            raw = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if raw is None:
                raise ValueError("Missing or invalid vision template: " + key)
            self._templates[key] = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
        return self._templates[key]

    def _match(self, image: np.ndarray, name: str, search: Area,
               threshold: float = 0.90, max_error: float = 20.0,
               path: Optional[Path] = None) -> Optional[Area]:
        template = self._template(path or ASSETS / (name + ".png"))
        region = _crop(image, search)
        if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
            return None
        scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(scores)
        h, w = template.shape[:2]
        if not np.isfinite(score) or score < threshold:
            return None
        matched = region[loc[1]:loc[1] + h, loc[0]:loc[0] + w]
        # Correlation alone accepts a dimmed dialog background. Absolute color
        # error also has to pass before any identity/level/action is exposed.
        if float(cv2.absdiff(matched, template).mean()) > max_error:
            return None
        return search[0] + loc[0], search[1] + loc[1], w, h

    def is_courtyard(self, image: np.ndarray) -> bool:
        return bool(
            self._match(image, "buff", (350, 20, 53, 69), max_error=16)
            and self._match(image, "identity_frame", (312, 30, 34, 59), max_error=16)
            and self._match(image, "moon", (49, 98, 1033, 61), threshold=0.80,
                            max_error=35,
                            path=ROOT / "tasks/GameUi/page/page_check_main.png")
        )

    def read_level(self, image: np.ndarray) -> Optional[int]:
        crop = _crop(image, LEVEL_ROI)
        values = []
        for blue_min in (100, 140):
            # Gold badge borders are excluded; only pale glyph pixels survive.
            white = ((crop[:, :, 0] > 160) & (crop[:, :, 1] > 155)
                     & (crop[:, :, 2] > blue_min)).astype(np.uint8) * 255
            # Anti-aliased gold-border pixels otherwise look like punctuation.
            # Remove only tiny speckles, never crop to a single digit (30 must
            # not accidentally become 3 when the badge grows to two digits).
            count, labels, stats, _ = cv2.connectedComponentsWithStats(white)
            for index in range(1, count):
                if stats[index, cv2.CC_STAT_AREA] < 5:
                    white[labels == index] = 0
            if not 10 <= cv2.countNonZero(white) <= 250:
                return None
            text = self._read(cv2.cvtColor(white, cv2.COLOR_GRAY2RGB),
                              "level_" + str(blue_min))
            if not isinstance(text, str) or not re.fullmatch(r"[1-9][0-9]?", text):
                return None
            value = int(text)
            if not 1 <= value <= 60:
                return None
            values.append(value)
        return values[0] if values[0] == values[1] else None

    def read_identity(self, image: np.ndarray) -> Optional[str]:
        text = self._read(_crop(image, IDENTITY_ROI), "identity")
        if not isinstance(text, str):
            return None
        text = text.strip()
        if not 1 <= len(text) <= 16 or not re.fullmatch(r"[\w\u4e00-\u9fff·]+", text):
            return None
        return text

    def find_story_npc(self, image: np.ndarray) -> Optional[Area]:
        area = None
        for template in ("story_bubble", "story_bubble_moved", "story_bubble_native"):
            area = self._match(image, template, NPC_SEARCH_ROI,
                               threshold=0.88, max_error=28)
            if area is not None:
                break
        if area is None:
            return None
        return self._bubble_hit_area(image, area)

    @staticmethod
    def _bubble_hit_area(image: np.ndarray, area: Area,
                         ring_value_min: int = 115) -> Optional[Area]:
        bubble = _crop(image, area)
        h, w = bubble.shape[:2]
        hsv = cv2.cvtColor(bubble, cv2.COLOR_RGB2HSV)
        gold = cv2.inRange(hsv, (10, 65, ring_value_min), (40, 230, 255))
        yy, xx = np.mgrid[:h, :w]
        radius = np.sqrt((xx - w / 2) ** 2 + (yy - h / 2) ** 2)
        ring = (radius >= 22) & (radius <= 30)
        if np.count_nonzero(gold[ring]) < 110:
            return None
        # Exactly three small pale, horizontally aligned dots inside the ring.
        inside = bubble[20:39, 10:w - 10]
        pale = ((inside[:, :, 0] > 175) & (inside[:, :, 1] > 145)
                & (inside[:, :, 2] > 145)).astype(np.uint8) * 255
        count, _, stats, centers = cv2.connectedComponentsWithStats(pale)
        dots = [centers[i] for i in range(1, count)
                if 7 <= stats[i, cv2.CC_STAT_AREA] <= 55
                and 2 <= stats[i, cv2.CC_STAT_WIDTH] <= 10
                and 2 <= stats[i, cv2.CC_STAT_HEIGHT] <= 10]
        if len(dots) != 3:
            return None
        dots = sorted(dots, key=lambda p: p[0])
        if max(p[1] for p in dots) - min(p[1] for p in dots) > 3:
            return None
        if any(not 8 <= dots[i + 1][0] - dots[i][0] <= 16 for i in (0, 1)):
            return None
        # Small inner hit area, never the entire template/search rectangle.
        return area[0] + 20, area[1] + 20, 20, 18

    def _story_layout_clear(self, image: np.ndarray) -> bool:
        """Check static layout while accepting measured local idle animation.

        Independent small anchors alone could survive a dialogue/modal drawn
        elsewhere. Per-pixel RGB bounds come from the first capture and six
        even-numbered frames of a real 12-frame idle sequence; the other six
        frames are held-out regression data. Static pixels keep their original
        bounds, instead of relaxing the whole image or ignoring all characters.
        Only the NPC bubble ROI is independent of page identity: losing its
        target must not prevent a verified back button from restoring identity.
        """
        return self._layout_with_motion_bounds(image, "story_scene", (STORY_NPC_SEARCH_ROI,))

    def _layout_with_motion_bounds(self, image: np.ndarray, prefix: str,
                                    excluded_areas: Tuple[Area, ...] = ()) -> bool:
        """Supplement independent anchors with observed local motion bounds."""
        reference = self._template(ASSETS / (prefix + "_layout.png"))
        minimum = self._template(ASSETS / (prefix + "_motion_min.png"))
        maximum = self._template(ASSETS / (prefix + "_motion_max.png"))
        reduced = cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA)
        if float(reduced.mean()) < float(reference.mean()) * 0.98:
            return False
        difference = cv2.max(cv2.subtract(minimum, reduced), cv2.subtract(reduced, maximum))
        if prefix == "story_eye_camera1":
            characters = np.zeros(reduced.shape[:2], dtype=bool)
            for x, y, width, height in CAMERA1_CHARACTER_ROIS:
                characters[y // 4:(y + height + 3) // 4,
                           x // 4:(x + width + 3) // 4] = True
            # Known pose/animation may vary only in observed foreground areas.
            # Everywhere else uses the strict static reference, including the
            # environment, return control and gold-eye tutorial target.
            difference[~characters] = cv2.absdiff(reduced, reference)[~characters]
        for x, y, width, height in excluded_areas:
            difference[y // 4:(y + height + 3) // 4,
                       x // 4:(x + width + 3) // 4] = 0
        if float(difference.mean()) > 6.0:
            return False
        if float(np.mean(difference.max(axis=2) > 65)) > 0.035:
            return False
        # Local occlusion cannot be diluted into the mean of the whole screen.
        for y in range(0, 180, 20):
            for x in range(0, 320, 20):
                if float(difference[y:y + 20, x:x + 20].mean()) > 18.0:
                    return False
        return True

    def observe_story_scene(self, image: np.ndarray) -> Optional[VisionObservation]:
        # Two spatially independent fixed scene decorations plus the observed
        # back icon are mandatory. This is not a generic yellow-arrow matcher.
        tree = self._match(image, "story_tree_mark", (650, 120, 130, 115),
                           threshold=0.93, max_error=12)
        shrine = self._match(image, "story_shrine_window", (1086, 87, 169, 121),
                             threshold=0.93, max_error=12)
        if tree is None or shrine is None:
            if tree is not None or shrine is not None:
                return VisionObservation(reason="story_scene_anchors_unverified")
            return None
        back = self._match(image, "story_return", (10, 10, 65, 65),
                           threshold=0.95, max_error=10)
        if back is None:
            return VisionObservation(reason="story_return_unverified")
        if not self._story_layout_clear(image):
            return VisionObservation(reason="story_layout_changed")
        bubble = self._match(image, "story_scene_bubble", STORY_NPC_SEARCH_ROI,
                             threshold=0.92, max_error=15)
        area = self._bubble_hit_area(image, bubble, ring_value_min=80) if bubble else None
        tanuki = self._match(image, "story_tanuki_bubble", STORY_TANUKI_SEARCH_ROI,
                             threshold=0.95, max_error=10)
        tanuki_area = self._bubble_hit_area(image, tanuki, ring_value_min=80) if tanuki else None
        reentry = self._match(image, "story_reentry_bubble", (430, 285, 105, 100),
                              threshold=0.95, max_error=10)
        reentry_area = self._bubble_hit_area(image, reentry, ring_value_min=80) if reentry else None
        if sum(target is not None for target in (area, tanuki_area, reentry_area)) > 1:
            return VisionObservation(reason="story_scene_multiple_npcs")
        if tanuki_area is not None:
            area = tanuki_area
        if reentry_area is not None:
            area = reentry_area
        return VisionObservation(
            page="story_scene", npc_story_area=area,
            return_area=(back[0] + 14, back[1] + 14, 24, 24),
            evidence=("story_tree_mark", "story_shrine_window", "story_return_icon",
                      "story_layout_clear") + (("story_npc_ring_three_dots",) if area else ()) +
                      (("tanuki_dialogue_target",) if tanuki_area else ()),
            reason=("verified_reentry_story_npc" if reentry_area else
                    "verified_tanuki_story_npc" if tanuki_area else
                    "verified_story_scene_npc" if area else "story_npc_unstable"),
        )

    def observe_story2_scene(self, image: np.ndarray) -> Optional[VisionObservation]:
        """Only the recorded second tree camera: Xiaobai dialogue or eye hint.

        Neither a generic skip button nor an eye elsewhere authorizes an action.
        Static scenery/back must match first; each UI variant has independent
        positive anchors and a separate observed-motion/occlusion envelope.
        """
        tree = self._match(image, "story2_tree", (741, 121, 118, 131),
                           threshold=0.95, max_error=10)
        shrine = self._match(image, "story2_shrine", (1180, 82, 100, 131),
                             threshold=0.95, max_error=10)
        if tree is None or shrine is None:
            return None
        back = self._match(image, "story_return", (10, 10, 65, 65),
                           threshold=0.95, max_error=10)
        if back is None:
            return VisionObservation(reason="story2_return_unverified")
        return_area = (back[0] + 14, back[1] + 14, 24, 24)
        skip = self._match(image, "dialogue_skip", (816, 544, 111, 60),
                           threshold=0.95, max_error=10)
        speaker = self._match(image, "dialogue_speaker", (335, 548, 87, 55),
                              threshold=0.95, max_error=10)
        panel = self._match(image, "dialogue_panel", (5, 629, 230, 86),
                            threshold=0.94, max_error=10)
        if skip is not None or speaker is not None or panel is not None:
            if skip is None or speaker is None or panel is None:
                return VisionObservation(reason="story_dialogue_anchors_unverified")
            if not self._layout_with_motion_bounds(image, "story_dialogue"):
                return VisionObservation(reason="story_dialogue_layout_changed")
            return VisionObservation(
                page="story_dialogue", return_area=return_area,
                story_skip_area=(skip[0] + 20, skip[1] + 10, 48, 20),
                evidence=("story2_tree", "story2_shrine", "story_return_icon",
                          "xiaobai_speaker", "dialogue_panel", "explicit_story_skip",
                          "dialogue_motion_layout_clear"),
                reason="verified_story_dialogue_skip",
            )
        return self._observe_eye(image, return_area, "story_eye",
                                 ("story2_tree", "story2_shrine"))

    def observe_story1_eye(self, image: np.ndarray) -> Optional[VisionObservation]:
        """Courtyard re-entry preserves the eye hint but restores camera 1.

        The screen-space eye overlaps the old camera-1 tree-mark crop. Match
        the unobstructed tree paper charm and original shrine instead. Do not
        widen camera-2 search regions or reinterpret a failed camera as motion.
        """
        paper = self._match(image, "story1_tree_paper", (750, 295, 148, 105),
                            threshold=0.95, max_error=10)
        shrine = self._match(image, "story_shrine_window", (1086, 87, 169, 121),
                             threshold=0.95, max_error=10)
        if paper is None or shrine is None:
            return None
        back = self._match(image, "story_return", (10, 10, 65, 65),
                           threshold=0.95, max_error=10)
        if back is None:
            return VisionObservation(reason="story_camera1_return_unverified")
        if (self._match(image, "dialogue_skip", (816, 544, 111, 60),
                        threshold=0.95, max_error=10)
                or self._match(image, "dialogue_panel", (5, 629, 230, 86),
                               threshold=0.94, max_error=10)):
            return VisionObservation(reason="story_camera1_dialogue_unverified")
        return self._observe_eye(image, (back[0] + 14, back[1] + 14, 24, 24),
                                 "story_eye_camera1", ("camera1_tree_paper", "camera1_shrine"))

    def _observe_eye(self, image: np.ndarray, return_area: Area, layout_prefix: str,
                     camera_evidence: Tuple[str, ...]) -> VisionObservation:
        eye = self._match(image, "tutorial_eye", (564, 79, 152, 154),
                          threshold=0.95, max_error=10)
        if eye is None:
            return VisionObservation(reason="story_eye_unverified")
        target = _crop(image, eye)
        hsv = cv2.cvtColor(target, cv2.COLOR_RGB2HSV)
        gold = cv2.inRange(hsv, (15, 110, 150), (40, 255, 255))
        yy, xx = np.mgrid[:134, :132]
        radius = np.sqrt((xx - 66) ** 2 + (yy - 67) ** 2)
        if np.count_nonzero(gold[(radius >= 57) & (radius <= 68)]) < 1800:
            return VisionObservation(reason="story_eye_ring_unverified")
        if np.count_nonzero(target[40:95, 35:100].min(axis=2) > 170) < 1100:
            return VisionObservation(reason="story_eye_symbol_unverified")
        if not self._layout_with_motion_bounds(image, layout_prefix):
            return VisionObservation(reason=layout_prefix + "_layout_changed")
        return VisionObservation(
            page="story_eye", return_area=return_area,
            tutorial_area=(eye[0] + 44, eye[1] + 51, 44, 34),
            evidence=camera_evidence + ("story_return_icon",
                      "gold_ring_white_eye", "no_dialogue_anchors", "eye_motion_layout_clear"),
            reason="verified_story_eye_target",
        )

    def observe_story_reveal(self, image: np.ndarray) -> Optional[VisionObservation]:
        """Recognize the observed camera-1 selective-darkness reveal effect.

        The three normal characters stay brightly colored while known scenery
        is dark and roaming purple ghosts cross the middle. We deliberately do
        not fit a whole-frame ghost pose or gamma-correct a modal/black screen.
        """
        shrine = self._match(image, "reveal_shrine", (1091, 92, 159, 111),
                             threshold=0.98, max_error=2)
        mountain = self._match(image, "reveal_mountain", (110, 73, 140, 135),
                               threshold=0.98, max_error=2)
        floor = self._match(image, "reveal_floor", (320, 590, 720, 110),
                            threshold=0.98, max_error=2)
        if shrine is None or mountain is None or floor is None:
            return None
        # Fine flicker in the dark paper changes raw correlation. Blur only
        # this fixed background crop, retaining a tight absolute-color limit;
        # this is neither a global gamma adjustment nor relaxed page matching.
        paper = cv2.GaussianBlur(_crop(image, (455, 156, 110, 76)), (0, 0), 3)
        paper_verified = False
        for index in range(4):
            template = cv2.GaussianBlur(self._template(ASSETS / ("reveal_paper_" + str(index) + ".png")), (0, 0), 3)
            score = float(cv2.matchTemplate(paper, template, cv2.TM_CCOEFF_NORMED)[0, 0])
            if np.isfinite(score) and score >= 0.95 and float(cv2.absdiff(paper, template).mean()) <= 3:
                paper_verified = True
                break
        if not paper_verified:
            return VisionObservation(reason="story_reveal_paper_unverified")
        back = self._match(image, "reveal_return", (10, 10, 65, 65),
                           threshold=0.95, max_error=10)
        if back is None:
            return VisionObservation(reason="story_reveal_return_unverified")
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        regions = (
            ((120, 390, 115, 120), (160, 70, 100), (179, 255, 255), 0.30),
            ((585, 295, 110, 125), (80, 100, 120), (115, 255, 255), 0.14),
            ((1060, 280, 125, 140), (10, 60, 130), (40, 255, 255), 0.07),
        )
        brightness = []
        for area, low, high, minimum_fraction in regions:
            region = _crop(hsv, area)
            fraction = cv2.countNonZero(cv2.inRange(region, low, high)) / (area[2] * area[3])
            if fraction < minimum_fraction:
                return VisionObservation(reason="story_reveal_bright_characters_unverified")
            brightness.append(float(_crop(image, area).mean()))
        if not 90 <= float(np.mean(brightness)) <= 108:
            return VisionObservation(reason="story_reveal_selective_lighting_unverified")
        # A normal modal/confirmation/old dialogue may preserve scenery edges,
        # but cannot inherit the known question-mark target from that alone.
        question = self._match(image, "reveal_question", (860, 254, 79, 85),
                               threshold=0.92, max_error=14)
        glyph = self._match(image, "reveal_question_glyph", (884, 273, 31, 44),
                            threshold=0.98, max_error=10)
        if question is None or glyph is None:
            return VisionObservation(reason="story_reveal_question_unverified")
        if abs(glyph[0] - question[0] - 19) > 2 or abs(glyph[1] - question[1] - 14) > 2:
            return VisionObservation(reason="story_reveal_question_alignment_unverified")
        return VisionObservation(
            page="story_reveal", npc_story_area=(glyph[0] + 2, glyph[1] + 4, 16, 26),
            return_area=(back[0] + 14, back[1] + 14, 24, 24),
            evidence=("dark_camera1_paper", "dark_camera1_shrine", "dark_mountain",
                      "clear_dark_floor", "three_bright_characters", "selective_lighting",
                      "brown_question_bubble", "white_question_glyph", "story_return_icon"),
            reason="verified_story_reveal_npc",
        )

    def observe(self, image: np.ndarray) -> VisionObservation:
        result = self._observe_known(image)
        if result.page != "unknown":
            return result
        # Passive recognition never overrides a known action or grants one.
        # A new speaker can auto-advance while the runner retains its finite
        # no-action timeout; it must not become a generic skip/return target.
        from tasks.NewbieLeveling.dialogue_wait import observe_dialogue_wait
        from tasks.NewbieLeveling.cinematic_widgets import observe_cinematic_widgets
        try:
            normalized = normalize_frame(image)
            cinematic = observe_cinematic_widgets(normalized, self)
            if cinematic is not None:
                return VisionObservation(**cinematic)
            dialogue_wait = observe_dialogue_wait(normalized, self)
        except (ValueError, TypeError):
            dialogue_wait = None
        return VisionObservation(**dialogue_wait) if dialogue_wait else result

    def _observe_known(self, image: np.ndarray) -> VisionObservation:
        try:
            image = normalize_frame(image)
            if not self.is_courtyard(image):
                from tasks.NewbieLeveling.dialogue_widgets import observe_dialogue_widgets
                # Keep Xiaobai's existing strict layout/negative cases intact.
                # Only the recorded cat/Kagura dialogues use the reusable
                # widget branch here; a generic skip alone grants no action.
                dialogue = observe_dialogue_widgets(
                    image, self, allowed_speakers=('jiumingmao', 'kagura', 'xiaobai_reentry'))
                if dialogue is not None:
                    return VisionObservation(**dialogue)
                from tasks.NewbieLeveling.post_cinematic import observe_post_cinematic
                post_cinematic = observe_post_cinematic(image, self)
                if post_cinematic is not None:
                    return VisionObservation(**post_cinematic)
                from tasks.NewbieLeveling.reveal_widgets import observe_reveal_widgets
                reveal_widgets = observe_reveal_widgets(image, self)
                # A recognized scene with missing/ambiguous controls is an
                # authoritative refusal, not permission for a fixed target.
                if reveal_widgets is not None:
                    return VisionObservation(**reveal_widgets)
                reveal = self.observe_story_reveal(image)
                if reveal is not None and reveal.page != "unknown":
                    return reveal
                story = self.observe_story_scene(image)
                if story is not None and story.page != "unknown":
                    return story
                story1_eye = self.observe_story1_eye(image)
                if story1_eye is not None and story1_eye.page != "unknown":
                    return story1_eye
                story2 = self.observe_story2_scene(image)
                if story2 is not None:
                    return story2
                if story1_eye is not None:
                    return story1_eye
                if story is not None:
                    return story
                if reveal is not None:
                    return reveal
                return VisionObservation(reason="courtyard_anchors_missing")
            level = self.read_level(image)
            identity = self.read_identity(image)
            if level is None or identity is None:
                return VisionObservation(page="courtyard", level=level, identity=identity,
                                         evidence=("courtyard_anchors",),
                                         reason="account_ocr_untrusted")
            area = self.find_story_npc(image)
            return VisionObservation(page="courtyard", level=level, identity=identity,
                                     npc_story_area=area,
                                     evidence=("courtyard_anchors", "account_badge_dual_ocr",
                                               "account_identity_ocr") +
                                              (("npc_gold_ring_three_dots",) if area else ()),
                                     reason="verified_story_npc" if area else "no_verified_story_action")
        except Exception as exc:
            return VisionObservation(reason="vision_error:" + type(exc).__name__)
