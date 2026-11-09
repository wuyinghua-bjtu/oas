"""Offline recognition of the recorded Forest Investigation movie chrome.

There are TWO real movie frames: 20260909-000220-430566-paused.png and
1788883370334642700-00.png. The supplied 01/02 captures are already back in
the forest and are negative fixtures, not additional movie calibrations.
All cinematic_* assets are unchanged crops of the first movie frame.

Only fixed title/frame/playback/input widgets are matched. Moving actors,
subtitles, user-authored barrage text and input content are never matched or
read with OCR. The rightmost >| icon is not the repository's existing
explicit-text skip template. Until its exact behavior is independently
verified, this detector is deliberately WAIT ONLY: no playback, skip, back,
checkbox, input or send action is exposed.

Use a finite runner wait timeout and session budget. A match does not prove
progress. Dimming or overlays crossing any required anchor fail closed; an
arbitrary overlay wholly within the ignored animation cannot be excluded.
This limitation cannot create a click because every action area stays None.
"""

from pathlib import Path

import cv2
import numpy as np


ASSETS = Path(__file__).with_name('vision_assets')
# Screen-space, 1280x720 RGB. No animation/text-body/portrait templates.
SCENE_ROIS = {
    'forest_heading': (565, 0, 145, 42),
    'frame_left': (15, 2, 225, 68),
    'frame_right': (793, 2, 170, 38),
}
CONTROL_ROIS = {
    'pause': (979, 24, 70, 69),
    'fast_forward': (1080, 24, 70, 69),
    'end_icon': (1180, 24, 70, 69),
    'barrage_label': (135, 664, 62, 38),
    'barrage_checkbox': (207, 660, 48, 49),
    'input_top': (365, 657, 555, 6),
    'input_bottom': (365, 702, 555, 8),
    'input_left': (361, 663, 6, 38),
    'input_right': (917, 663, 6, 38),
    'send': (948, 652, 135, 65),
}


def _matches(image, vision, name, area):
    path = ASSETS / ('cinematic_' + name + '.png')
    if vision._match(image, path.stem, area, threshold=0.98,
                     max_error=2.0, path=path) is None:
        return False
    x, y, width, height = area
    actual = image[y:y + height, x:x + width]
    expected = vision._template(path)
    if actual.shape != expected.shape:
        return False
    # Absolute foreground color prevents correlation from accepting a dimmed
    # title/button. Dark decorative frame crops need only the strict match.
    foreground = expected.max(axis=2) > 90
    return (np.count_nonzero(foreground) < 15
            or float(cv2.absdiff(actual, expected)[foreground].mean()) <= 3.0)


def observe_cinematic_widgets(image, vision):
    """Return VisionObservation-compatible story_cinematic_wait data or None.

    No optional permissive/action flag exists. Keep exact known dialogue
    detections separate; this output must never authorize a generic skip.
    """
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
            or image.shape != (720, 1280, 3)):
        return None
    try:
        if not all(_matches(image, vision, name, area)
                   for name, area in {**SCENE_ROIS, **CONTROL_ROIS}.items()):
            return None
    except (ValueError, OSError, cv2.error):
        return None
    return {
        'page': 'story_cinematic_wait',
        'reason': 'verified_forest_cinematic_wait_only_unverified_skip',
        'evidence': ('forest_investigation_heading', 'left_and_right_movie_frame',
                     'three_playback_icons', 'barrage_label_and_checkbox',
                     'four_input_borders', 'send_widget_without_action',
                     'animation_and_barrage_unread',
                     'end_icon_action_semantics_unverified', 'wait_only'),
        'npc_story_area': None,
        'return_area': None,
        'story_skip_area': None,
        'tutorial_area': None,
    }
