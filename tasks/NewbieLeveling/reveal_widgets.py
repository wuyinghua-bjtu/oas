"""Local reveal-page controls shared by the two recorded dark cameras.

No devices, OCR, network or model calls. None means no recorded scene matched;
an unknown dict is authoritative after partial/complete scene recognition.
The runner must require stable observations and its account/session guards.
"""
from pathlib import Path

import cv2
import numpy as np


ASSETS = Path(__file__).with_name("reveal_widget_assets")
LEGACY_ASSETS = Path(__file__).with_name("vision_assets")
NPC_BAND = (130, 230, 1000, 150)
CAMERAS = (
    {
        "name": "camera1",
        "anchors": (("reveal_shrine", (1091, 92, 159, 111)),
                    ("reveal_mountain", (110, 73, 140, 135)),
                    ("reveal_floor", (320, 590, 720, 110))),
        "paper": (455, 156, 110, 76), "paper_names": tuple("reveal_paper_" + str(i) for i in range(4)),
        "colors": (((120, 390, 115, 120), (160, 70, 100), (179, 255, 255), .30),
                   ((585, 295, 110, 125), (80, 100, 120), (115, 255, 255), .14),
                   ((1060, 280, 125, 140), (10, 60, 130), (40, 255, 255), .07)),
        "brightness": (90, 108),
    },
    {
        "name": "camera3",
        "anchors": (("camera3_shrine", (990, 91, 184, 104)),
                    ("camera3_mountain", (23, 75, 155, 130)),
                    ("camera3_floor", (320, 590, 720, 110))),
        "paper": (338, 160, 105, 70), "paper_names": tuple("camera3_paper_" + str(i) for i in range(3)),
        "colors": (((195, 370, 145, 120), (165, 60, 120), (179, 255, 255), .11),
                   ((610, 298, 85, 120), (80, 80, 100), (120, 255, 255), .17),
                   ((880, 280, 135, 140), (10, 60, 130), (40, 255, 255), .07)),
        "brightness": (82, 99),
    },
)


def _crop(image, area):
    x, y, width, height = area
    return image[y:y + height, x:x + width]


def _path(name):
    return (ASSETS if name.startswith("camera3_") else LEGACY_ASSETS) / (name + ".png")


def _match(vision, image, name, area, threshold=.98, max_error=2):
    return vision._match(image, name, area, threshold=threshold, max_error=max_error, path=_path(name))


def _unknown(reason, camera=""):
    return {"page": "unknown", "npc_story_area": None, "return_area": None,
            "evidence": (camera,) if camera else (), "reason": reason}


def _paper_verified(image, vision, camera):
    paper = cv2.GaussianBlur(_crop(image, camera["paper"]), (0, 0), 3)
    for name in camera["paper_names"]:
        template = cv2.GaussianBlur(vision._template(_path(name)), (0, 0), 3)
        score = float(cv2.matchTemplate(paper, template, cv2.TM_CCOEFF_NORMED)[0, 0])
        if np.isfinite(score) and score >= .95 and float(cv2.absdiff(paper, template).mean()) <= 3:
            return True
    return False


def _bright_characters(image, camera):
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    brightness = []
    for area, low, high, fraction_min in camera["colors"]:
        fraction = cv2.countNonZero(cv2.inRange(_crop(hsv, area), low, high)) / (area[2] * area[3])
        if fraction < fraction_min:
            return False
        brightness.append(float(_crop(image, area).mean()))
    low, high = camera["brightness"]
    return low <= float(np.mean(brightness)) <= high


def _question_targets(image, vision):
    """Find unique question widgets, not ghosts or arbitrary pale dots.

    Search the observed NPC band for the white question glyph. Its fixed offset
    must align with the reused brown-ring template. A ring-only mask avoids
    fitting the animated ghost/background through the translucent bubble.
    """
    glyph = vision._template(_path("reveal_question_glyph"))
    bubble = vision._template(_path("reveal_question"))
    hsv = cv2.cvtColor(bubble, cv2.COLOR_RGB2HSV)
    ring_mask = cv2.inRange(hsv, (4, 40, 55), (35, 245, 230))
    yy, xx = np.mgrid[:65, :59]
    radius = np.sqrt((xx - 29.5) ** 2 + (yy - 29) ** 2)
    annulus = (radius > 23) & (radius < 30)
    ring_mask[~annulus] = 0
    scores = cv2.matchTemplate(_crop(image, NPC_BAND), glyph, cv2.TM_CCOEFF_NORMED)
    count, labels, _, _ = cv2.connectedComponentsWithStats((scores >= .98).astype(np.uint8))
    if count > 12:
        return []
    targets = []
    for index in range(1, count):
        masked_scores = np.where(labels == index, scores, -1)
        _, _, _, (x, y) = cv2.minMaxLoc(masked_scores)
        x += NPC_BAND[0]
        y += NPC_BAND[1]
        actual_glyph = _crop(image, (x, y, 21, 34))
        if float(cv2.absdiff(actual_glyph, glyph).mean()) > 10:
            continue
        actual_ring = _crop(image, (x - 19, y - 14, 59, 65))
        ring_score = float(cv2.matchTemplate(actual_ring, bubble, cv2.TM_CCORR_NORMED,
                                             mask=ring_mask)[0, 0])
        if not np.isfinite(ring_score) or ring_score < .98:
            continue
        brown = cv2.inRange(cv2.cvtColor(actual_ring, cv2.COLOR_RGB2HSV),
                            (4, 40, 55), (35, 245, 230))
        if np.count_nonzero(brown[annulus]) < 260:
            continue
        target = (x + 2, y + 4, 16, 26)
        if not any(abs(target[0] - old[0]) <= 8 and abs(target[1] - old[1]) <= 8 for old in targets):
            targets.append(target)
    return targets


def _eye_target(image, vision):
    """The closing-eye glyph is distinct from the earlier opening-eye glyph.

    Asset is an unchanged (574,89,132,134) crop of the first recorded closing
    hint; two later independently captured frames are regression holdouts.
    """
    eye = _match(vision, image, "reveal_close_eye", (564, 79, 152, 154), threshold=.95, max_error=10)
    if eye is None:
        return None
    target = _crop(image, eye)
    gold = cv2.inRange(cv2.cvtColor(target, cv2.COLOR_RGB2HSV), (15, 110, 150), (40, 255, 255))
    yy, xx = np.mgrid[:134, :132]
    radius = np.sqrt((xx - 66) ** 2 + (yy - 67) ** 2)
    if np.count_nonzero(gold[(radius >= 57) & (radius <= 68)]) < 1800:
        return None
    if np.count_nonzero(target[40:95, 35:100].min(axis=2) > 170) < 1100:
        return None
    return (eye[0] + 44, eye[1] + 51, 44, 34)


def observe_reveal_widgets(image, vision):
    """Return verified page/control dict, authoritative unknown, or no match."""
    if not isinstance(image, np.ndarray) or image.shape != (720, 1280, 3) or image.dtype != np.uint8:
        return _unknown("reveal_widget_invalid_frame")
    camera = None
    partial = None
    for candidate in CAMERAS:
        matched = sum(_match(vision, image, name, area) is not None for name, area in candidate["anchors"])
        if matched == len(candidate["anchors"]):
            camera = candidate
            break
        if matched >= 2:
            partial = candidate["name"]
    if camera is None:
        return _unknown("reveal_widget_scene_incomplete", partial) if partial else None
    name = camera["name"]
    if not _paper_verified(image, vision, camera):
        return _unknown("reveal_widget_paper_unverified", name)
    back = _match(vision, image, "reveal_return", (10, 10, 65, 65), threshold=.95, max_error=10)
    if back is None:
        return _unknown("reveal_widget_return_unverified", name)
    eye_area = _eye_target(image, vision) if name == "camera1" else None
    lighting = camera
    if eye_area is not None:
        # A separate observed tutorial phase, not a relaxed NPC detector.
        # Static dark scenery/paper and an exact closing glyph must match
        # before these phase-specific foreground ranges can be used.
        lighting = dict(camera, colors=(
            ((120, 390, 115, 120), (160, 70, 100), (179, 255, 255), .20),
            ((585, 295, 110, 125), (80, 100, 120), (115, 255, 255), .10),
            ((1060, 280, 125, 140), (10, 60, 130), (40, 255, 255), .07),
        ), brightness=(80, 94))
    if not _bright_characters(image, lighting):
        return _unknown("reveal_widget_selective_lighting_unverified", name)
    if (_match(vision, image, "dialogue_skip", (816, 544, 111, 60), threshold=.95, max_error=10)
            or _match(vision, image, "dialogue_panel", (5, 629, 230, 86), threshold=.94, max_error=10)):
        return _unknown("reveal_widget_dialogue_or_modal", name)
    targets = _question_targets(image, vision)
    if eye_area is not None:
        if targets or name != "camera1":
            return _unknown("reveal_widget_conflicting_or_uncalibrated_eye", name)
        # After the ghost dialogue, the same verified dark camera prompts
        # closing the eye. No arbitrary tutorial hand or global click target.
        return {"page": "story_eye", "npc_story_area": None,
                "tutorial_area": eye_area, "return_area": (29, 29, 24, 24),
                "evidence": (name, "dark_environment_anchors", "paper_charm", "bright_characters",
                             "no_dialogue_controls", "no_question_targets", "gold_ring_white_eye"),
                "reason": "verified_reveal_close_eye"}
    if len(targets) != 1:
        return _unknown("reveal_widget_question_missing" if not targets else "reveal_widget_question_ambiguous", name)
    # Returning from the courtyard resets the camera, not quest progress:
    # the recorded camera-1 target changes from cat (891,282) to ghost
    # (781,278). Camera 3 also contains that ghost at (580,278). Bind to the
    # known central NPC band, not one NPC coordinate. Search the larger band
    # first so duplicate questions outside this action band still block input.
    if not (500 <= targets[0][0] <= 1000 and 230 <= targets[0][1] <= 350):
        return _unknown("reveal_widget_camera1_target_unverified", name)
    return {"page": "story_reveal", "npc_story_area": targets[0],
            "return_area": (back[0] + 14, back[1] + 14, 24, 24),
            "evidence": (name, "dark_environment_anchors", "paper_charm", "bright_characters",
                         "no_dialogue_controls", "unique_question_glyph_aligned_brown_ring", "reveal_return"),
            "reason": "verified_reveal_widget"}
