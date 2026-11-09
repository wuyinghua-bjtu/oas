"""Create an invitation-only room from an already selected activity list."""
import time

from tasks.Component.GeneralRoom.assets import GeneralRoomAssets as Room
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite


_ACTIVITY_NAMES = {'experience': '经验妖怪', 'gold': '金币妖怪', 'tako': '石距'}


def create_private_room(device, activity, timeout=20):
    """Never confirm creation unless activity title and private mode match.

    Navigation and invitation are separate, so this function must not be used
    as evidence that a particular apprentice has joined.
    """
    if activity not in _ACTIVITY_NAMES:
        raise ValueError('未知师徒副本')
    expected = _ACTIVITY_NAMES[activity]
    deadline = time.monotonic() + timeout
    stage = 'select'
    last_click = 0.0
    while time.monotonic() < deadline:
        device.screenshot()
        image = device.image
        now = time.monotonic()
        if stage == 'select':
            # Require the exact activity title before invoking a paid creation.
            title = ''.join(str(Room.O_GR_ZONES_NAME.ocr(image)).split())
            # The installed OCR reads 妖 as 缺 on the current gold title;
            # the leading two characters uniquely identify this list entry.
            matches_title = (title == expected
                             or (activity == 'gold' and title.startswith('金币') and len(title) == 4)
                             or (activity == 'tako' and title.startswith('石距') and len(title) <= 3))
            if not matches_title or not Room.I_CREATE_ROOM.match(image):
                time.sleep(.2)
                continue
            device.click(*Room.I_CREATE_ROOM.coord(), control_name='mentorship_create_room')
            stage, last_click = 'dialog', now
        elif stage == 'dialog':
            if Room.I_ENSURE_PRIVATE.match(image):
                private, confirm = True, Room.I_CREATE_ENSURE
            elif Room.I_ENSURE_PRIVATE_2.match(image):
                private, confirm = True, Room.I_CREATE_ENSURE_2
            elif Room.I_ENSURE_PRIVATE_FALSE.match(image):
                private, confirm = False, Room.I_ENSURE_PRIVATE_FALSE
            elif Room.I_ENSURE_PRIVATE_FALSE_2.match(image):
                private, confirm = False, Room.I_ENSURE_PRIVATE_FALSE_2
            else:
                time.sleep(.2)
                continue
            if now - last_click < .8:
                time.sleep(.2)
                continue
            if not private:
                device.click(*confirm.coord(), control_name='mentorship_room_private')
                last_click = now
            elif confirm.match(image):
                device.click(*confirm.coord(), control_name='mentorship_create_confirm')
                stage, last_click = 'room', now
        elif (Invite.I_ADD_5_4.match(image) if activity != 'tako'
              else Invite.I_ADD_1.match(image) and Invite.I_ADD_2.match(image)):
            return True
        time.sleep(.2)
    return False
