"""Read guardian attempts only on the verified exploration activity screen."""
import time

from module.atom.ocr import RuleOcr
from .vision import detect

_COUNTER = RuleOcr(roi=(1138, 264, 45, 29), area=(1138, 264, 45, 29),
                   mode='DigitCounter', method='Default', keyword='',
                   name='mentorship_guard_remaining')
_COUNTER_WITH_REFRESH = RuleOcr(roi=(1138, 239, 45, 29), area=(1138, 239, 45, 29),
                                mode='DigitCounter', method='Default', keyword='',
                                name='mentorship_guard_remaining_refresh')


def read_remaining(device, timeout=8, counter=_COUNTER):
    """Two matching readings are required; malformed OCR never means zero."""
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        device.screenshot()
        image = device.image
        if not detect(image, 'guard_entry'):
            previous = None
        else:
            counters = (counter, _COUNTER_WITH_REFRESH) if counter is _COUNTER else (counter,)
            values = []
            for item in counters:
                current, _, total = item.ocr(image)
                if total == 5 and 0 <= current <= total:
                    values.append(current)
            value = values[0] if values and len(set(values)) == 1 else None
            if value is not None and value == previous:
                return value
            previous = value
        time.sleep(.2)
    return None
