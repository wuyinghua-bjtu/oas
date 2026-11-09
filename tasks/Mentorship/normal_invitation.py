"""Invitation handshake for normal private rooms.

The recipient starts listening before the sender is allowed to invite.
Both invitation identity and the joined room are checked by the caller's
activity-specific recognizers; an ambiguous banner is never accepted.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path

import cv2
import numpy as np

from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite

_ASSETS = Path(__file__).parent / 'assets'


def invitation_position(frame, activity):
    """Identify the master's portrait and the requested invitation beside it."""
    if activity not in ('experience', 'gold', 'tako'):
        raise ValueError('尚无该副本的邀请识别')
    if activity == 'tako':
        from module.atom.ocr import RuleOcr
        reader = RuleOcr(roi=(190,205,260,100), area=(190,205,260,100),
                         mode='Full', method='Default', keyword='', name='mentor_stone_invite_text')
        words = ''.join(''.join(r.ocr_text.split()) for r in reader.detect_and_ocr(frame))
        avatar = cv2.imdecode(np.fromfile(str(_ASSETS / 'mentor_avatar.png'), np.uint8), cv2.IMREAD_COLOR)
        region = cv2.cvtColor(frame[205:305,190:285], cv2.COLOR_RGB2BGR)
        avatar_match = (avatar is not None and region.shape[0] >= avatar.shape[0]
                        and region.shape[1] >= avatar.shape[1]
                        and cv2.matchTemplate(region, avatar, cv2.TM_CCOEFF_NORMED).max() >= .9)
        if not (avatar_match or 'OASPlayer' in words) or '石距' not in words:
            return None
        patch = frame[235:270,120:160].astype(np.int16)
        green = (patch[:,:,1] > patch[:,:,0] + 18) & (patch[:,:,1] > patch[:,:,2] + 8)
        return (140,250) if green.mean() > .2 else None
    region = cv2.cvtColor(frame[190:500, :500], cv2.COLOR_RGB2BGR)
    def match(name):
        template = cv2.imdecode(np.fromfile(str(_ASSETS / name), np.uint8), cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(name)
        _, score, _, point = cv2.minMaxLoc(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED))
        return score, (point[0], point[1] + 190)
    score, (x, y) = match(activity + '_invitation.png')
    avatar_score, (ax, ay) = match('mentor_avatar.png')
    if score < .9 or avatar_score < .85 or abs(ax - (x - 78)) > 8 or abs(ay - (y + 2)) > 8:
        from module.atom.ocr import RuleOcr
        reader = RuleOcr(roi=(190,205,260,100), area=(190,205,260,100),
                         mode='Full', method='Default', keyword='', name='mentor_normal_invite_text')
        words = ''.join(''.join(r.ocr_text.split()) for r in reader.detect_and_ocr(frame))
        label = '经验妖怪' if activity == 'experience' else '金币妖怪'
        if 'OASPlayer' not in words or label not in words:
            return None
        patch = frame[235:270,120:160].astype(np.int16)
        green = (patch[:,:,1] > patch[:,:,0] + 18) & (patch[:,:,1] > patch[:,:,2] + 8)
        return (140,250) if green.mean() > .2 else None
    cx, cy = x - 138, y + 32
    if cx < 16 or cy < 16:
        return None
    patch = frame[cy-15:cy+16, cx-15:cx+16].astype(np.int16)
    green = (patch[:, :, 1] > patch[:, :, 0] + 18) & (patch[:, :, 1] > patch[:, :, 2] + 8)
    return (cx, cy) if green.mean() > .2 else None


def experience_invitation_position(frame):
    return invitation_position(frame, 'experience')


def accept_invitation(device, matches_invitation, matches_room, ready, timeout=15):
    deadline = time.monotonic() + timeout
    clicked = False
    last_click = 0.0
    saved = False
    ready.set()
    while time.monotonic() < deadline:
        device.screenshot()
        frame = device.image
        if clicked:
            path = Path('log/mentorship/normal_after_accept.png')
            cv2.imencode('.png', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))[1].tofile(str(path))
        if not saved and deadline - time.monotonic() < timeout - 2:
            path = Path('log/mentorship/normal_invite_live.png')
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imencode('.png', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))[1].tofile(str(path))
            saved = True
        if clicked and matches_room(frame):
            return True
        now = time.monotonic()
        position = matches_invitation(frame)
        if position and now - last_click >= 1:
            device.click(*position, control_name='mentorship_accept_invitation')
            clicked, last_click = True, now
        time.sleep(.15)
    return False


def invite_with_listener(device, send, matches_invitation, matches_room, timeout=15):
    ready = Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(accept_invitation, device, matches_invitation,
                             matches_room, ready, timeout)
        if not ready.wait(2) or not send():
            return False
        return result.result()
