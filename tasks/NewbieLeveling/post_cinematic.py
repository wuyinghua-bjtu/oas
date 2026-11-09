"""Recorded post-movie forest camera, local controls only; no device or OCR.

Static background/footer crops exclude the animated actors. Bubble matching
uses a local translucent control crop plus an independent ring/three-dot test.
Unobserved cameras, ambiguous NPCs or missing evidence have no actions.
This does not recognize arbitrary overlays leaving every sampled area intact.
"""
from pathlib import Path

import cv2
import numpy as np

ASSETS = Path(__file__).with_name('vision_assets')
SCENE_ROIS = {
    'mountain': (100, 90, 200, 130),
    'tree': (642, 135, 103, 100),
    'shrine': (1060, 95, 174, 103),
    'floor_left': (50, 530, 140, 110),
    'floor_center': (520, 500, 160, 70),
    'floor_low_left': (340, 570, 140, 110),
    'floor_low_right': (800, 570, 140, 110),
    'floor_right': (1100, 530, 140, 110),
}
BUBBLE_ROI = (470, 282, 60, 62)
SEARCH_ROI = (350, 230, 700, 170)
POST_DIALOGUE_SCENE_ROIS = {
    'mountain': (100, 70, 150, 160),
    'tree': (680, 70, 100, 110),
    'shrine': (1170, 80, 100, 130),
    'floor_left': (50, 590, 140, 100),
    'floor_low_left': (340, 620, 140, 70),
    'floor_center': (820, 490, 180, 90),
    'floor_low_right': (800, 600, 140, 70),
    'floor_right': (1100, 550, 140, 110),
}
POST_DIALOGUE_BUBBLE_ROI = (1186, 204, 60, 62)
POST_DIALOGUE_SEARCH_ROI = (1160, 190, 115, 110)


def _observe_camera3(image, vision):
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
            or image.shape != (720, 1280, 3)):
        return None
    try:
        for name, area in SCENE_ROIS.items():
            path = ASSETS / ('post_cinematic_' + name + '.png')
            if vision._match(image, path.stem, area, threshold=.97,
                             max_error=3.0, path=path) is None:
                return None
        back = vision._match(image, 'story_return', (10, 10, 65, 65),
                             threshold=.95, max_error=10)
        if back is None:
            return None
        template = vision._template(ASSETS / 'post_cinematic_bubble.png')
        x, y, width, height = SEARCH_ROI
        region = image[y:y + height, x:x + width]
        scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
        th, tw = template.shape[:2]
        targets = []
        # Suppress overlapping matches; any second verified target is refused.
        for _ in range(8):
            _, score, _, (bx, by) = cv2.minMaxLoc(scores)
            if score < .95:
                break
            crop = region[by:by + th, bx:bx + tw]
            if float(cv2.absdiff(crop, template).mean()) <= 10:
                area = vision._bubble_hit_area(image, (x + bx, y + by, tw, th),
                                               ring_value_min=80)
                if area is not None:
                    targets.append(area)
            scores[max(0, by - 20):by + 21, max(0, bx - 20):bx + 21] = -1
        if len(targets) != 1:
            return None
        area = targets[0]
        if not (470 <= area[0] <= 525 and 280 <= area[1] <= 335):
            return None
        return {
            'page': 'story_scene', 'npc_story_area': area,
            'return_area': (back[0] + 14, back[1] + 14, 24, 24),
            'reason': 'verified_post_cinematic_umbrella_npc',
            'evidence': ('post_cinematic_static_camera', 'clear_sampled_floor',
                         'story_return_icon', 'unique_local_ring_three_dots'),
        }
    except (ValueError, OSError, cv2.error):
        return None


def _observe_camera4(image, vision):
    """Only the independently recorded post-dialogue right-side NPC camera."""
    try:
        for name, area in POST_DIALOGUE_SCENE_ROIS.items():
            path = ASSETS / ('post_dialogue_' + name + '.png')
            if vision._match(image, path.stem, area, threshold=.97,
                             max_error=3.0, path=path) is None:
                return None
        back = vision._match(image, 'story_return', (10, 10, 65, 65),
                             threshold=.95, max_error=10)
        if back is None:
            return None
        template = vision._template(ASSETS / 'post_dialogue_bubble.png')
        x, y, width, height = POST_DIALOGUE_SEARCH_ROI
        region = image[y:y + height, x:x + width]
        scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
        th, tw = template.shape[:2]
        targets = []
        for _ in range(8):
            _, score, _, (bx, by) = cv2.minMaxLoc(scores)
            if score < .95:
                break
            crop = region[by:by + th, bx:bx + tw]
            if float(cv2.absdiff(crop, template).mean()) <= 10:
                area = vision._bubble_hit_area(image, (x + bx, y + by, tw, th),
                                               ring_value_min=80)
                if area is not None:
                    targets.append(area)
            scores[max(0, by - 20):by + 21, max(0, bx - 20):bx + 21] = -1
        if len(targets) != 1:
            return None
        return {
            'page': 'story_scene', 'npc_story_area': targets[0],
            'return_area': (back[0] + 14, back[1] + 14, 24, 24),
            'reason': 'verified_post_dialogue_tanuki_npc',
            'evidence': ('post_dialogue_static_camera', 'clear_sampled_floor',
                         'story_return_icon', 'unique_local_ring_three_dots'),
        }
    except (ValueError, OSError, cv2.error):
        return None


def observe_post_cinematic(image, vision):
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
            or image.shape != (720, 1280, 3)):
        return None
    result = _observe_camera3(image, vision)
    if result is not None:
        return result
    return _observe_camera4(image, vision)
