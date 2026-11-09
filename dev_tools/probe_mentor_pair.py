"""Probe one private-room invitation, then leave without starting a fight."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import cv2
from module.config.config import Config
from tasks.Mentorship.device import BoundDevice, validate_profiles
from tasks.Mentorship.private_room import create_private_room
from tasks.Mentorship.guardian_device import _selected
from tasks.Mentorship.identity import find_guard_candidate
from tasks.Mentorship.normal_invitation import experience_invitation_position
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite

mc, ac = Config('oas1'), Config('oas_leveling')
validate_profiles(mc, ac)
m, a = BoundDevice(mc), BoundDevice(ac)

def wait_for(d, pred, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        d.screenshot()
        if pred(d.image):
            return True
        time.sleep(.2)
    return False

def listen(ready):
    ready.set()
    end = time.monotonic() + 12
    while time.monotonic() < end:
        a.screenshot()
        position = experience_invitation_position(a.image)
        if position:
            path = os.path.join(os.environ['TEMP'], 'mentorship-invitation.png')
            cv2.imencode('.png', cv2.cvtColor(a.image, cv2.COLOR_RGB2BGR))[1].tofile(path)
            print('CAPTURED', path, flush=True)
            a.click(*position, control_name='probe_accept')
            if wait_for(a, Invite.I_GI_IN_ROOM.match, 8):
                for name, device in [('mentor', m), ('apprentice', a)]:
                    device.screenshot()
                    path = os.path.join(os.environ['TEMP'], 'mentorship-room-'+name+'.png')
                    cv2.imencode('.png', cv2.cvtColor(device.image, cv2.COLOR_RGB2BGR))[1].tofile(path)
                print('JOINED', flush=True)
                return True
            return False
        time.sleep(.2)
    print('NO_INVITATION', flush=True)
    return False

created = False
try:
    created = create_private_room(m, 'experience')
    if not created:
        raise RuntimeError('Private room was not confirmed')
    m.click(420, 295, control_name='probe_invite_open')
    if not wait_for(m, Invite.I_INVITE_ENSURE.match):
        raise RuntimeError('Invitation list not found')
    candidate = None
    for _ in range(15):
        m.screenshot()
        candidate = find_guard_candidate(m.image, '冥界画师03')
        if candidate:
            break
        time.sleep(.3)
    print('CANDIDATE', candidate, flush=True)
    if not candidate:
        raise RuntimeError('Apprentice not recognized')
    m.click(*candidate, control_name='probe_select_apprentice')
    if not wait_for(m, lambda image: _selected(image, candidate)):
        raise RuntimeError('Selection not confirmed')
    ready = Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(listen, ready)
        ready.wait(2)
        m.click(775, 574, control_name='probe_send_invite')
        result.result()
finally:
    if created:
        # A departing leader transfers leadership to the remaining player.
        # Leave the apprentice first so no unattended timed room remains.
        a.screenshot()
        if Invite.I_GI_IN_ROOM.match(a.image):
            a.click(46, 38, control_name='probe_apprentice_exit')
            from module.atom.ocr import RuleOcr
            prompt = RuleOcr(roi=(468,290,340,65), area=(468,290,340,65), mode='Single', method='Default', keyword='', name='mentorship_apprentice_exit_prompt')
            if not wait_for(a, lambda image: '退出组队' in prompt.ocr(image), 5):
                raise RuntimeError('Apprentice exit dialog not confirmed')
            a.click(755, 435, control_name='probe_apprentice_exit_confirm')
            if not wait_for(a, lambda image: not Invite.I_GI_IN_ROOM.match(image), 8):
                raise RuntimeError('Apprentice room exit not confirmed')
        m.screenshot()
        if Invite.I_INVITE_ENSURE.match(m.image):
            m.click(500, 575, control_name='probe_cancel')
            time.sleep(.5)
        m.click(46, 38, control_name='probe_exit')
        from module.atom.ocr import RuleOcr
        exit_text = RuleOcr(roi=(468,290,340,65), area=(468,290,340,65), mode='Single', method='Default', keyword='', name='mentorship_exit_prompt')
        if wait_for(m, lambda image: '退出组队' in exit_text.ocr(image), 5):
            m.click(755, 435, control_name='probe_exit_confirm')
        if not wait_for(m, lambda image: not Invite.I_GI_IN_ROOM.match(image), 8):
            raise RuntimeError('Room exit not confirmed')
        print('ROOM_LEFT', flush=True)
