"""Record the current online friend list and safely leave the test room."""
import os
import time
import cv2
from module.config.config import Config
from tasks.Mentorship.device import BoundDevice, validate_profiles
from tasks.Mentorship.private_room import create_private_room
from tasks.Mentorship.normal_device import NormalDevices
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite

mc, ac = Config('oas1'), Config('oas_leveling')
validate_profiles(mc, ac)
m, a = BoundDevice(mc), BoundDevice(ac)
pair = NormalDevices(m, a, '冥界画师03')
created = False
try:
    created = create_private_room(m, 'experience')
    if not created:
        raise RuntimeError('未确认创建经验房间')
    m.click(420, 295, control_name='probe_friend_list')
    time.sleep(3)
    m.screenshot()
    if not Invite.I_INVITE_ENSURE.match(m.image):
        raise RuntimeError('未找到好友列表')
    path = os.path.join(os.environ['TEMP'], 'mentorship-friend-list.png')
    cv2.imencode('.png', cv2.cvtColor(m.image, cv2.COLOR_RGB2BGR))[1].tofile(path)
    print('CAPTURED', path, flush=True)
finally:
    if created:
        print('BOTH_LEFT', pair.leave_both(), flush=True)
