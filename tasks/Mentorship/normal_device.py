"""Bounded private-room invitation and two-device identity checks."""
import time
import numpy as np
from module.atom.ocr import RuleOcr

from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite
from tasks.GameUi.assets import GameUiAssets as Game
from .guardian_device import _selected
from .identity import find_guard_candidate, normal_rooms_have_pair
from .normal_invitation import invitation_position, invite_with_listener
from .room_exit import leave_team_room
from .vision import detect


def _dismiss_game_junior_invitation(device):
    """Dismiss the game's floating junior suggestion before inviting by name."""
    reader = RuleOcr(roi=(270, 205, 205, 55), area=(270, 205, 205, 55),
                     mode='Full', method='Default', keyword='', name='mentorship_junior_prompt')
    words = ''.join(item.ocr_text for item in reader.detect_and_ocr(device.image)).replace(' ', '')
    if '邀请后辈加入' not in words:
        return False
    patch = device.image[230:272, 24:66].astype(np.int16)
    red = (patch[:, :, 0] > patch[:, :, 1] + 25) & (patch[:, :, 0] > patch[:, :, 2] + 20)
    if red.mean() < .12:
        return False
    device.click(47, 250, control_name='mentorship_dismiss_junior_prompt')
    return True


class NormalDevices:
    def __init__(self, mentor, apprentice, name, read_name=None):
        self.mentor = mentor
        self.apprentice = apprentice
        self.name = name
        self.read_name = read_name

    @staticmethod
    def _wait(device, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            device.screenshot()
            value = predicate(device.image)
            if value:
                return value
            time.sleep(.2)
        return None

    def pair_confirmed(self):
        self.mentor.screenshot()
        self.apprentice.screenshot()
        result = normal_rooms_have_pair(self.mentor.image, self.apprentice.image,
                                       self.name, self.read_name)
        if not result:
            import cv2
            from pathlib import Path
            for label, device in (('mentor', self.mentor), ('apprentice', self.apprentice)):
                path = Path('log/mentorship') / ('normal_identity_' + label + '.png')
                path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imencode('.png', cv2.cvtColor(device.image, cv2.COLOR_RGB2BGR))[1].tofile(str(path))
        return result

    def leave_both(self):
        """Leave the guest first, so the leader cannot transfer to it."""
        failures = []
        for label, device in (('徒弟', self.apprentice), ('师父', self.mentor)):
            try:
                device.screenshot()
                frame = device.image
                if Invite.I_INVITE_ENSURE.match(frame):
                    device.click(500, 575, control_name='mentorship_cancel_invite')
                    if not self._wait(device, lambda image: not Invite.I_INVITE_ENSURE.match(image), 5):
                        failures.append(label)
                        continue
                    frame = device.image
                if Invite.I_GI_IN_ROOM.match(frame):
                    if not leave_team_room(device):
                        failures.append(label)
                elif not (Game.I_CHECK_MAIN.match(frame) or Game.I_CHECK_TEAM.match(frame)
                          or detect(frame, 'guard_entry')):
                    failures.append(label)
            except Exception:
                failures.append(label)
        if failures:
            raise RuntimeError('无法确认退出房间：' + '、'.join(failures))
        return True

    def invite_and_join(self, activity):
        """Return only after both clients show the configured pair."""
        if activity not in ('experience', 'gold', 'tako'):
            raise ValueError('该副本邀请画面尚未验证')
        m, a = self.mentor, self.apprentice
        success = False
        try:
            add = Invite.I_ADD_1 if activity == 'tako' else Invite.I_ADD_5_1
            # A floating invitation can temporarily cover the first empty
            # slot as the room opens. Wait for the confirmed room and slot.
            def room_and_slot(frame):
                if _dismiss_game_junior_invitation(m):
                    return False
                return Invite.I_GI_IN_ROOM.match(frame) and add.match(frame)
            if not self._wait(m, room_and_slot, timeout=12):
                from pathlib import Path
                import cv2
                path = Path('log/mentorship/normal_room_unrecognized.png')
                path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imencode('.png', cv2.cvtColor(m.image, cv2.COLOR_RGB2BGR))[1].tofile(str(path))
                return False
            m.click(*add.coord(), control_name='mentorship_invite_open')
            if not self._wait(m, Invite.I_INVITE_ENSURE.match):
                return False
            candidate = self._wait(m, lambda image: find_guard_candidate(image, self.name, self.read_name))
            if not candidate:
                return False
            m.click(*candidate, control_name='mentorship_select_apprentice')
            if not self._wait(m, lambda image: _selected(image, candidate), 5):
                return False

            def send():
                m.screenshot()
                if not Invite.I_INVITE_ENSURE.match(m.image) or not _selected(m.image, candidate):
                    return False
                m.click(775, 574, control_name='mentorship_send_invitation')
                return True

            if not invite_with_listener(a, send, lambda frame: invitation_position(frame, activity),
                                        Invite.I_GI_IN_ROOM.match):
                return False
            success = self.pair_confirmed()
            return success
        finally:
            if not success:
                self.leave_both()
