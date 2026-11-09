"""Recognize the SDK's expired-login modal before another click is sent."""
import time

from module.atom.ocr import RuleOcr
from module.exception import RequestHumanTakeover


def install_login_expiry_guard(device, window_name):
    original = device.screenshot
    box = (388, 225, 504, 270)
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                     keyword='', name='group_login_expired')
    last_check = 0.0

    def guarded_screenshot():
        nonlocal last_check
        result = original()
        image = device.image
        if time.monotonic() - last_check >= 1 and image[225:495, 388:892, :3].mean() > 210:
            last_check = time.monotonic()
            words = ''.join(row.ocr_text for row in reader.detect_and_ocr(image)).replace(' ', '')
            if '登录已失效' in words and '重新登录' in words:
                raise RequestHumanTakeover(f'{window_name} 的网易账号登录已失效，请手动重新登录')
        return result

    device.screenshot = guarded_screenshot
    return original
