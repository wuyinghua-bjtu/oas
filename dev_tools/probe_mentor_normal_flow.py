"""Exercise the experience room handshake and leave both without fighting."""
import sys
from module.config.config import Config
from tasks.Mentorship.device import BoundDevice, validate_profiles
from tasks.Mentorship.normal_device import NormalDevices
from tasks.Mentorship.private_room import create_private_room

mc, ac = Config('oas1'), Config('oas_leveling')
validate_profiles(mc, ac)
master, apprentice = BoundDevice(mc), BoundDevice(ac)
pair = NormalDevices(master, apprentice, '冥界画师03')
created = False
activity = sys.argv[1] if len(sys.argv) > 1 else 'experience'
try:
    created = create_private_room(master, activity)
    if not created:
        raise RuntimeError('房间创建未确认')
    joined = pair.invite_and_join(activity)
    print('JOINED_AND_VERIFIED', joined, flush=True)
    if not joined:
        raise RuntimeError('邀请或双端身份未确认')
finally:
    if created:
        print('BOTH_LEFT', pair.leave_both(), flush=True)
