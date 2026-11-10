"""Capture a gold invitation and leave the temporary room without fighting."""
import os
from module.config.local_values import local_text
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import cv2
import numpy as np
from module.config.config import Config
from tasks.Mentorship.device import BoundDevice, validate_profiles
from tasks.Mentorship.private_room import create_private_room
from tasks.Mentorship.identity import find_guard_candidate
from tasks.Mentorship.guardian_device import _selected
from tasks.Mentorship.normal_device import NormalDevices
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite

mc, ac = Config('oas1'), Config('oas_leveling')
validate_profiles(mc, ac)
m, a = BoundDevice(mc), BoundDevice(ac)
pair = NormalDevices(m, a, local_text('LOCAL_OCR_NAME03'))

def wait(d, pred, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        d.screenshot()
        result = pred(d.image)
        if result:
            return result
        time.sleep(.2)
    return None

def capture(ready):
    ready.set()
    end = time.monotonic() + 15
    while time.monotonic() < end:
        a.screenshot()
        image = a.image
        for y in range(225, 461, 4):
            patch = image[y-12:y+13, 128:153].astype(np.int16)
            green = (patch[:,:,1] > patch[:,:,0]+18) & (patch[:,:,1] > patch[:,:,2]+8)
            if green.mean() > .35:
                path = os.path.join(os.environ['TEMP'], 'mentorship-gold-invitation.png')
                cv2.imencode('.png', cv2.cvtColor(image, cv2.COLOR_RGB2BGR))[1].tofile(path)
                print('CAPTURED', path, flush=True)
                return True
        time.sleep(.15)
    return False

created = False
try:
    created = create_private_room(m, 'gold')
    if not created:
        raise RuntimeError('金币房间未确认创建')
    m.click(420, 295, control_name='probe_gold_invite_open')
    if not wait(m, Invite.I_INVITE_ENSURE.match):
        raise RuntimeError('邀请列表未出现')
    candidate = wait(m, lambda frame: find_guard_candidate(frame, local_text('LOCAL_OCR_NAME03')))
    if not candidate:
        raise RuntimeError('未识别徒弟')
    m.click(*candidate, control_name='probe_gold_select')
    if not wait(m, lambda frame: _selected(frame, candidate)):
        raise RuntimeError('未确认选择徒弟')
    ready = Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(capture, ready)
        ready.wait(2)
        m.click(775, 574, control_name='probe_gold_send')
        if not result.result():
            raise RuntimeError('未捕获邀请提示')
finally:
    if created:
        print('BOTH_LEFT', pair.leave_both(), flush=True)
