"""Recorded forest-story dialogue widgets, independent of character animation.

Only Xiaobai's ordinary/re-entry forest cameras, Jiumingmao's dark forest
camera, and Kagura's dark camera-1 dialogue are calibrated. Each variant has ONE original
dialogue screenshot; no synthetic
frame is calibration evidence. UI controls stay in screen-space, while three
independent environment crops bind them to the recorded forest/camera. There
is no OCR, game/device access, generic confirmation, or whole-frame pose fit.

All dialogue_widget_* PNGs are unchanged RGB crops at WIDGET_ROIS/SCENES from
log/newbie_leveling/oas_leveling/20260908-214201-488032-paused.png (Xiaobai) and
20260908-223754-617569-paused.png (Jiumingmao). Original fixtures are respectively
story_dialogue_1280.png and dialogue_widget_cat_1280.png; no generated frames.
Kagura crops come from 20260908-232140-436180-paused.png, preserved unchanged
as dialogue_widget_kagura_1280.png. Its footer is the unoccupied bottom-center
patch, not the animated portrait covering the older bottom-left panel ROI.
Xiaobai's normally lit re-entry crops come only from
20260909-003257-933705-paused.png, saved as dialogue_widget_xiaobai_reentry_1280.png.
A second real frame, 1788885217951768900-00.png, is saved as
dialogue_widget_seimei_reentry_1280.png. Its Seimei name is NOT whitelisted;
the shared camera/chrome can only support the separate passive-wait detector.

The caller owns account binding, two fresh observations, action/transition
budgets and execution. Unchecked foreground pixels are intentionally not a
proof that every conceivable overlay has been excluded.
"""

from pathlib import Path

import cv2
import numpy as np


ASSETS = Path(__file__).with_name('vision_assets')
WIDGET_ROIS = {
    'skip': (826, 554, 91, 40),
    'speaker': (335, 552, 159, 39),
    'divider': (340, 593, 585, 16),
    'panel': (10, 634, 220, 76),
    'return': (15, 15, 54, 55),
}
WIDGET_ROI_OVERRIDES = {
    'kagura': {'panel': (350, 660, 550, 45)},
    'xiaobai_reentry': {'panel': (350, 660, 550, 45)},
}
# Do not mix controls from one recorded variant with the other's environment.
SCENES = {
    'xiaobai': {'mountain': (200, 90, 130, 140),
                'tree': (751, 131, 98, 111),
                'shrine': (1190, 92, 90, 111)},
    'jiumingmao': {'mountain': (200, 90, 130, 140),
                  'tree': (510, 90, 130, 130),
                  'shrine': (1002, 90, 158, 120)},
    'kagura': {'mountain': (115, 78, 130, 125),
              'tree': (570, 65, 130, 135),
              'shrine': (1096, 97, 149, 101)},
    'xiaobai_reentry': {'mountain': (100, 70, 150, 160),
                        'tree': (680, 70, 100, 110),
                        'shrine': (1170, 80, 100, 130)},
}


def _crop(image, area):
    x, y, width, height = area
    return image[y:y + height, x:x + width]


def _asset(speaker, component):
    return ASSETS / ('dialogue_widget_' + speaker + '_' + component + '.png')


def _orange_mask(image):
    # Orange glyphs only, excluding changing clothing/scene behind the label.
    return cv2.inRange(cv2.cvtColor(image, cv2.COLOR_RGB2HSV),
                       (4, 140, 155), (26, 255, 255)) > 0


def _speaker_matches(image, vision, speaker):
    actual = _crop(image, WIDGET_ROIS['speaker'])
    expected = vision._template(_asset(speaker, 'speaker'))
    actual_mask, expected_mask = _orange_mask(actual), _orange_mask(expected)
    if min(int(actual_mask.sum()), int(expected_mask.sum())) < 80:
        return False
    intersection = int(np.count_nonzero(actual_mask & expected_mask))
    dice = 2 * intersection / (int(actual_mask.sum()) + int(expected_mask.sum()))
    if dice < 0.90:
        return False
    # A darkened/covered name must not pass on normalized glyph shape alone.
    return float(cv2.absdiff(actual, expected)[expected_mask].mean()) <= 4.0


def _widget_matches(image, vision, speaker, component):
    area = WIDGET_ROI_OVERRIDES.get(speaker, {}).get(component, WIDGET_ROIS[component])
    path = _asset(speaker, component)
    if vision._match(image, path.stem, area, threshold=0.95,
                     max_error=4.0, path=path) is None:
        return False
    if component == 'panel':
        return True
    actual, expected = _crop(image, area), vision._template(path)
    foreground = expected.max(axis=2) > 90
    if np.count_nonzero(foreground) < 15:
        return False
    # Correlation and whole-crop mean can hide dimmed bright button lettering.
    return float(cv2.absdiff(actual, expected)[foreground].mean()) <= 4.0


def observe_dialogue_widgets(image, vision, *,
                             allowed_speakers=('xiaobai', 'jiumingmao', 'kagura',
                                               'xiaobai_reentry')):
    """Return only verified story skip/back areas, otherwise None.

    Accepts an already-normalized native RGB uint8 frame and a NewbieVision
    instance for cached template loading/matching. No identity, level, tutorial
    target, purchase, or generic confirm action is inferred from this detector.
    Runtime may allow only Jiumingmao while preserving the older, stricter
    Xiaobai detector. Unknown whitelist names never introduce new variants.
    """
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
            or image.shape != (720, 1280, 3)):
        return None
    try:
        for speaker, scenery in SCENES.items():
            if speaker not in allowed_speakers:
                continue
            if not _speaker_matches(image, vision, speaker):
                continue
            if not all(vision._match(
                    image, 'dialogue_widget_' + speaker + '_' + name, area,
                    threshold=0.97, max_error=2.0,
                    path=_asset(speaker, name)) is not None
                    for name, area in scenery.items()):
                continue
            if not all(_widget_matches(image, vision, speaker, name)
                       for name in ('return', 'skip', 'divider', 'panel')):
                continue
            return {
                'page': 'story_dialogue',
                'story_skip_area': (846, 564, 48, 20),
                'return_area': (29, 29, 24, 24),
                'evidence': ('dialogue_widget_' + speaker + '_speaker',
                             'dialogue_widget_' + speaker + '_mountain',
                             'dialogue_widget_' + speaker + '_tree',
                             'dialogue_widget_' + speaker + '_shrine',
                             'explicit_story_skip', 'story_return_icon',
                             'gold_dialogue_divider', 'recorded_dialogue_footer'),
                'reason': 'verified_' + speaker + '_dialogue_widgets',
            }
    except (ValueError, OSError, cv2.error):
        # Missing/corrupt assets or malformed input never authorize a click.
        return None
    return None
