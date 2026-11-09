"""Conservative identification of the configured apprentice in a list."""
from pathlib import Path
import cv2
import numpy as np


DEFAULT_NAME = '冥界画师03'


def guard_room_has_apprentice(image, name, read_name=None):
    """Confirm the configured nickname in the guest slot of a guardian room."""
    if name == DEFAULT_NAME:
        path = Path(__file__).parent / 'assets' / 'guard_room_default_name.png'
        template = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(path)
        region = cv2.cvtColor(image[85:160, 800:1035], cv2.COLOR_RGB2BGR)
        return float(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED).max()) >= 0.90
    if read_name is None:
        return False
    results = read_name(image)
    return len([text for text, (x, y, w, h) in results
                if 800 <= x < 1035 and 85 <= y < 160
                and ''.join(text.split()) == ''.join(name.split())]) == 1


def both_guard_rooms_have_apprentice(mentor_image, apprentice_image, name, read_name=None):
    return (guard_room_has_apprentice(mentor_image, name, read_name)
            and guard_room_has_apprentice(apprentice_image, name, read_name))


def normal_rooms_have_pair(mentor_image, apprentice_image, name, read_name=None):
    """Verify both names on both recorded five-player room layouts."""
    if name != DEFAULT_NAME:
        if read_name is None:
            return False
        observed = []
        for frame in (mentor_image, apprentice_image):
            names = [text.replace(' ', '') for text, (x, y, w, h) in read_name(frame)
                     if 50 <= x < 800 and 90 <= y < 165]
            if names.count(name.replace(' ', '')) != 1:
                return False
            observed.append(names)
        # On the leader's screen the floating friend badge can cover the
        # leader nickname. The guest's screen independently shows both names.
        if observed[1].count('OASPlayer') != 1:
            return False
        return True
    root = Path(__file__).parent / 'assets'
    templates = []
    for filename in ('normal_guest_name.png', 'normal_master_name.png'):
        template = cv2.imdecode(np.fromfile(str(root / filename), np.uint8), cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(filename)
        templates.append(template)
    for frame in (mentor_image, apprentice_image):
        region = cv2.cvtColor(frame[90:165, 50:520], cv2.COLOR_RGB2BGR)
        if any(float(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED).max()) < .85
               for template in templates):
            return False
    return True


def find_guard_candidate(image, name, read_name=None):
    """Find a single exact candidate, or return None on uncertainty.

    The recorded glyph template is tied to the default nickname. Other names
    must be provided by an exact OCR result with a rectangle; no fuzzy match.
    """
    if name == DEFAULT_NAME:
        region = cv2.cvtColor(image[155:530, 345:935], cv2.COLOR_RGB2BGR)
        hits = []
        for filename in ('apprentice_default_name.png', 'apprentice_recent_name.png'):
            path = Path(__file__).parent / 'assets' / filename
            template = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
            if template is None:
                raise FileNotFoundError(path)
            scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(scores >= 0.94)
            for x, y in zip(xs, ys):
                hits.append((345 + int(x) + template.shape[1] // 2,
                             155 + int(y) + template.shape[0] // 2,
                             float(scores[y, x])))
        if not hits:
            return None
        # Both variants can match the same row; separate rows are ambiguous.
        xs, ys = [p[0] for p in hits], [p[1] for p in hits]
        if max(xs) - min(xs) > 10 or max(ys) - min(ys) > 10:
            return None
        x, y, _ = max(hits, key=lambda p: p[2])
        return x, y
    if read_name is None:
        return None
    candidates = [(text, rect) for text, rect in read_name(image)
                  if 345 <= rect[0] < 935 and 155 <= rect[1] < 530
                  and ''.join(text.split()) == ''.join(name.split())]
    if len(candidates) != 1:
        return None
    x, y, w, h = candidates[0][1]
    return x + w // 2, y + h // 2
