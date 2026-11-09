"""只识别已记录的师徒页面，不把未知画面当作成功。"""
from pathlib import Path
import cv2
import numpy as np

_ROOT = Path(__file__).parent / 'assets'
_RULES = {
    'guard_entry': ('guard_entry.png',(870,160,370,180)),
    'guard_invite_entry': ('guard_invite_entry.png',(750,200,250,200)),
    'guard_invite_title': ('guard_invite_title.png',(465,85,350,100)),
    'guard_invitation': ('guard_invitation.png',(80,190,440,110)),
    'guard_room': ('guard_room.png',(830,615,250,90)),
    'guard_challenge': ('guard_challenge.png',(1140,575,140,145)),
    'guard_continue_prompt': ('guard_continue_prompt.png',(450,270,380,70)),
    'exploration_youkai': ('exploration_youkai.png',(200,600,180,120)),
    'orochi_selected_one': ('orochi_selected_one.png',(80,90,175,80)),
}


def detect(rgb_image, kind, threshold=0.85):
    filename, (x,y,w,h) = _RULES[kind]
    template = cv2.imdecode(np.fromfile(str(_ROOT / filename), dtype=np.uint8), cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(filename)
    image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    region = image[y:y+h,x:x+w]
    if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
        return None
    score, point = cv2.minMaxLoc(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED))[1::2]
    if score < threshold:
        return None
    return (x + point[0], y + point[1], template.shape[1], template.shape[0], score)


def guard_accept_position(rgb_image):
    """Locate the green accept control relative to the moving invitation."""
    match = detect(rgb_image, 'guard_invitation')
    if match is None:
        # The invitation portrait can be replaced by the level badge on the
        # exploration screen. Require the exact sender and activity text, as
        # well as the green accept button, before accepting that layout.
        from module.atom.ocr import RuleOcr
        reader = RuleOcr(roi=(190,210,260,95), area=(190,210,260,95),
                         mode='Full', method='Default', keyword='', name='mentor_guard_invite_text')
        words = ''.join(''.join(r.ocr_text.split()) for r in reader.detect_and_ocr(rgb_image))
        if 'OASPlayer' not in words or '守护历练' not in words:
            return None
        patch = rgb_image[235:270, 120:160].astype(np.int16)
        green = (patch[:, :, 1] > patch[:, :, 0] + 18) & (patch[:, :, 1] > patch[:, :, 2] + 8)
        return (140, 250) if green.mean() > .2 else None
    x, y, _, _, _ = match
    cx, cy = x - 137, y + 31
    if cx < 32 or cy < 32:
        return None
    # Only act on the green control, not the red reject or underlying page.
    patch = rgb_image[cy-15:cy+16, cx-15:cx+16].astype(np.int16)
    green = (patch[:, :, 1] > patch[:, :, 0] + 18) & (patch[:, :, 1] > patch[:, :, 2] + 8)
    return (cx, cy) if green.mean() > 0.2 else None


def lineup_state(rgb_image, threshold=0.8):
    """Return locked/unlocked only on a distinct, high-confidence match."""
    image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)[620:700,20:310]
    scores = {}
    for state in ('lock', 'unlock'):
        path = Path('tasks/Component/GeneralInvite/gi') / f'gi_{state}.png'
        template = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(path)
        scores[state] = float(cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED).max())
    best = max(scores, key=scores.get)
    other = 'unlock' if best == 'lock' else 'lock'
    if scores[best] < threshold or scores[best] - scores[other] < 0.1:
        return None
    return best
