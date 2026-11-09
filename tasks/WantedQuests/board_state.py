"""Conservative recognition of the current bounty board layout."""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

_ROOT = Path(__file__).parent / 'wq'


@lru_cache(maxsize=None)
def _template(name):
    template = cv2.imdecode(np.fromfile(str(_ROOT / name), dtype=np.uint8), cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(name)
    return template


def _score(image, rect, filename):
    x, y, w, h = rect
    region = image[y:y+h, x:x+w]
    template = _template(filename)
    if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
        return 0.0
    return float(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED).max())


def completed_reward_button(rgb_image):
    """Find the red claim button only while the bounty board is visible."""
    if not isinstance(rgb_image, np.ndarray) or rgb_image.shape[:2] != (720, 1280):
        return None
    image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    if _score(image, (545, 20, 190, 70), 'wq_board_header_sealed.png') < .9:
        return None
    template = _template('wq_claim_current.png')
    region = image[350:465, 100:1170]
    scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, point = cv2.minMaxLoc(scores)
    if score < .9:
        return None
    return (100 + point[0] + template.shape[1] // 2,
            350 + point[1] + template.shape[0] // 2)


def sealed_page_has_next(rgb_image):
    """Only recognize four sealed cards plus the visible next-page control.

    This does not say whether other pages are complete.
    """
    if not isinstance(rgb_image, np.ndarray) or rgb_image.shape[:2] != (720, 1280):
        return False
    image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    old_layout = (
        _score(image, (545, 20, 190, 70), 'wq_board_header_current.png') >= .9
        and _score(image, (1160, 330, 100, 80), 'wq_page_next_current.png') >= .88
        and all(_score(image, (x, 240, 100, 210), 'wq_sealed_current.png') >= .8
                for x in (175, 455, 735, 1015))
    )
    if old_layout:
        return True
    # The current completed-board appearance has different lighting, card
    # spacing and a friend banner over the first three seals. Match the same
    # unobstructed seal fragment on each card plus the board title and arrow.
    return (
        _score(image, (545, 20, 190, 70), 'wq_board_header_sealed.png') >= .9
        and _score(image, (1160, 330, 100, 80), 'wq_page_next_sealed.png') >= .9
        and all(_score(image, (x, 320, 100, 115), 'wq_sealed_footer.png') >= .88
                for x in (175, 445, 715, 985))
    )


def sealed_page_is_last(rgb_image):
    """Recognize a fully sealed last page with a previous-page arrow."""
    if not isinstance(rgb_image, np.ndarray) or rgb_image.shape[:2] != (720, 1280):
        return False
    image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    return (
        _score(image, (545, 20, 190, 70), 'wq_board_header_sealed.png') >= .9
        and _score(image, (60, 330, 95, 80), 'wq_page_previous_sealed.png') >= .9
        and _score(image, (1160, 330, 100, 80), 'wq_page_next_sealed.png') < .8
        and all(_score(image, (x, 320, 100, 115), 'wq_sealed_footer.png') >= .88
                for x in (175, 445, 715, 985))
    )
