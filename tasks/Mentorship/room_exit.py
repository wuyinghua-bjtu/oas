"""Bounded exit from a recognized team room, including the confirmation."""
import time
from module.atom.ocr import RuleOcr
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite
from tasks.GameUi.assets import GameUiAssets as Game

_PROMPT = RuleOcr(roi=(468, 290, 340, 65), area=(468, 290, 340, 65),
                  mode='Single', method='Default', keyword='', name='mentorship_room_exit')


def leave_team_room(device, timeout=10, returned=None):
    deadline = time.monotonic() + timeout
    back_clicked = confirmed = False
    last_click = 0
    while time.monotonic() < deadline:
        device.screenshot()
        frame = device.image
        now = time.monotonic()
        if (confirmed and not Invite.I_GI_IN_ROOM.match(frame)
                and (Game.I_CHECK_TEAM.match(frame) or Game.I_CHECK_MAIN.match(frame)
                     or (returned is not None and returned(frame)))):
            return True
        if back_clicked and '退出组队' in _PROMPT.ocr(frame):
            if now - last_click > .8:
                device.click(755, 435, control_name='mentorship_room_exit_confirm')
                last_click, confirmed = now, True
        elif not back_clicked and Invite.I_GI_IN_ROOM.match(frame):
            device.click(46, 38, control_name='mentorship_room_exit')
            last_click, back_clicked = now, True
        time.sleep(.2)
    return False
