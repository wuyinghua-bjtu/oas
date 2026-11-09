"""One-shot diagnostic: capture an invitation without accepting it."""
import os
import time
import cv2
from module.config.config import Config
from tasks.Mentorship.device import BoundDevice
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite

d = BoundDevice(Config('oas_leveling'))
print('LISTENING', flush=True)
end = time.monotonic() + 90
while time.monotonic() < end:
    d.screenshot()
    if Invite.I_I_ACCEPT.match(d.image):
        path = os.path.join(os.environ['TEMP'], 'mentorship-invitation.png')
        cv2.imencode('.png', cv2.cvtColor(d.image, cv2.COLOR_RGB2BGR))[1].tofile(path)
        print('CAPTURED', path, flush=True)
        break
    time.sleep(.1)
else:
    print('NO_INVITATION', flush=True)
