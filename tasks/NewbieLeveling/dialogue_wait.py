"""Recognize recorded forest dialogue chrome for bounded, action-free waiting.

Reuses the original normal/dark dialogue scenery and UI crops. A calibration
variant's name identifies its source screenshot, NOT the current speaker.
Speaker glyphs, dialogue text, portraits and whole-frame poses are not read.
No assets, observations, OCR or device operations are created by this module.

Call after exact known-speaker/action detectors. A match never authorizes a
skip, return, confirmation or tutorial action. The runner must retain its
session budget and a finite dialogue-wait timeout; this module neither proves
that text is advancing nor guarantees that the game will advance by itself.
"""

import cv2
import numpy as np

from tasks.NewbieLeveling.dialogue_widgets import SCENES, _asset, _widget_matches


def observe_dialogue_wait(image, vision):
    """Return a VisionObservation-compatible wait-only dict, or None.

    Input must already be a normalized native 1280x720 RGB uint8 frame. Each
    recorded variant still requires all three spatially independent scenery
    anchors, back icon, explicit skip, gold divider and unoccupied footer.
    Missing evidence is not relaxed just because no click will be issued.
    """
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
            or image.shape != (720, 1280, 3)):
        return None
    try:
        for variant, scenery in SCENES.items():
            if not all(vision._match(
                    image, 'dialogue_widget_' + variant + '_' + name, area,
                    threshold=0.97, max_error=2.0,
                    path=_asset(variant, name)) is not None
                    for name, area in scenery.items()):
                continue
            if not all(_widget_matches(image, vision, variant, name)
                       for name in ('return', 'skip', 'divider', 'panel')):
                continue
            return {
                'page': 'story_dialogue_wait',
                'reason': 'verified_forest_dialogue_wait_only',
                'evidence': ('recorded_camera_calibration:' + variant,
                             'forest_mountain', 'forest_tree', 'forest_shrine',
                             'back_and_skip_visible_without_action',
                             'gold_dialogue_divider', 'recorded_blank_footer',
                             'speaker_and_text_unverified', 'wait_only'),
                'npc_story_area': None,
                'return_area': None,
                'story_skip_area': None,
                'tutorial_area': None,
            }
    except (ValueError, OSError, cv2.error):
        return None
    return None
