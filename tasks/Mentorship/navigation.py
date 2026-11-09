"""Verified navigation and remaining attempts on 妖气探索."""
import time
from module.atom.ocr import RuleOcr
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_exploration
from .vision import detect

_YOUKAI_LABEL = RuleOcr(roi=(225, 670, 115, 45), area=(225, 670, 115, 45),
                        mode='Full', method='Default', keyword='', name='mentorship_youkai_label')

def _youkai_entry(image):
    match = detect(image, 'exploration_youkai')
    if match:
        x, y, w, h, _ = match
        return x + w // 2, y + h // 2
    words = ''.join(item.ocr_text for item in _YOUKAI_LABEL.detect_and_ocr(image)).replace(' ', '')
    if '妖气探索' in words:
        return 280, 655
    return None


def go_activity_menu(config, device, timeout=15):
    device.screenshot()
    if detect(device.image, 'guard_entry'):
        return True
    ui = GameUi(config, device)
    if not ui.ui_goto_page(page_exploration, timeout=30):
        return False
    device.screenshot()
    point = _youkai_entry(device.image)
    if not point:
        return False
    device.click(*point, control_name='mentorship_youkai_explore')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        device.screenshot()
        if detect(device.image, 'guard_entry'):
            return True
        time.sleep(.2)
    return False


def leave_activity_menu(device, timeout=10):
    device.screenshot()
    if not detect(device.image, 'guard_entry'):
        return False
    device.click(40, 35, control_name='mentorship_leave_youkai')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        device.screenshot()
        if _youkai_entry(device.image):
            return True
        time.sleep(.2)
    return False


_COUNTERS = {}
for name, y in (('experience', 240), ('gold', 512)):
    for suffix, offset in (('refresh', 0), ('full', 25)):
        rect = (305, y + offset, 45, 30)
        _COUNTERS[name, suffix] = RuleOcr(roi=rect, area=rect, mode='DigitCounter',
                                          method='Default', keyword='',
                                          name='mentorship_' + name + '_' + suffix)


def read_normal_remaining(device, activity, timeout=8):
    if activity not in ('experience', 'gold'):
        raise ValueError('unsupported activity counter')
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        device.screenshot()
        if not detect(device.image, 'guard_entry'):
            previous = None
        else:
            valid = []
            for suffix in ('refresh', 'full'):
                current, _, total = _COUNTERS[activity, suffix].ocr(device.image)
                if total == 2 and 0 <= current <= 2:
                    valid.append(current)
            value = valid[0] if valid and len(set(valid)) == 1 else None
            if value is not None and value == previous:
                return value
            previous = value
        time.sleep(.2)
    return None
