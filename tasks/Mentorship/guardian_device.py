"""Guardian-room operations using the two explicitly bound OAS devices.

Only recorded room screens are acted on. Unknown states fail closed; these
operations do not change accounts and do not start an OAS worker.
"""
import time

import cv2
import numpy as np

from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets
from .identity import find_guard_candidate, both_guard_rooms_have_apprentice
from .invitation import invite_guard_with_listener
from .lineup import lock_guard_lineups
from .vision import detect, lineup_state
from .room_exit import leave_team_room


def _selected(image, candidate):
    """Selected guardian invite tiles have a cyan background."""
    x, y = candidate
    x0, x1 = max(0, x - 90), min(image.shape[1], x + 105)
    y0, y1 = max(0, y - 20), min(image.shape[0], y + 40)
    patch = image[y0:y1, x0:x1]
    if not patch.size:
        return False
    hsv = cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)
    cyan = ((hsv[:, :, 0] >= 80) & (hsv[:, :, 0] <= 110)
            & (hsv[:, :, 1] >= 35) & (hsv[:, :, 2] >= 120))
    return float(np.mean(cyan)) >= .25


class GuardianDevices:
    def __init__(self, mentor, apprentice, name, read_name=None):
        self.mentor = mentor
        self.apprentice = apprentice
        self.name = name
        self.read_name = read_name

    @staticmethod
    def _capture(device):
        device.screenshot()
        return device.image

    @staticmethod
    def _wait(device, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            image = GuardianDevices._capture(device)
            value = predicate(image)
            if value:
                return value
            time.sleep(.2)
        return None

    def _both_confirmed(self, m, a):
        return both_guard_rooms_have_apprentice(m, a, self.name, self.read_name)

    def _leave_room(self):
        """Abort rather than leave an unverified room to auto-start."""
        m = self.mentor
        image = self._capture(m)
        if detect(image, 'guard_invite_title'):
            m.click(500, 575, control_name='mentor_guard_cancel_invite')
            if not self._wait(m, lambda frame: not detect(frame, 'guard_invite_title')
                              and detect(frame, 'guard_room'), timeout=5):
                return False
            image = m.image
        # The guest can become leader and keep the countdown after the master
        # exits, so explicitly leave it first when it is already in the room.
        a = self._capture(self.apprentice)
        if detect(a, 'guard_room') and not leave_team_room(self.apprentice):
            return False
        if detect(image, 'guard_entry'):
            return True
        if not detect(image, 'guard_room'):
            return False
        return leave_team_room(m, returned=lambda frame: bool(detect(frame, 'guard_entry')))

    def invite_and_lock(self):
        """Enter from the activity screen and verify both players and locks."""
        m = self.mentor
        image = self._capture(m)
        if not detect(image, 'guard_entry'):
            return False
        completed = False
        try:
            # The menu can still be settling after a settlement. Retry only
            # while the confirmed activity menu is visible; never send a
            # second click once the room or another screen has appeared.
            entered = False
            for attempt in range(3):
                image = self._capture(m)
                if detect(image, 'guard_invite_entry'):
                    entered = True
                    break
                if not detect(image, 'guard_entry'):
                    break
                m.click(1065, 220, control_name='mentor_guard_entry')
                if self._wait(m, lambda frame: detect(frame, 'guard_invite_entry'), timeout=8):
                    entered = True
                    break
                time.sleep(1)
            if not entered:
                m.save_screenshot(genre='mentorship_guard_entry_failed', interval=0)
                return False
            m.click(890, 270, control_name='mentor_guard_invite')
            if not self._wait(m, lambda frame: detect(frame, 'guard_invite_title')):
                return False
            candidate = find_guard_candidate(m.image, self.name, self.read_name)
            if candidate is None:
                return False
            m.click(*candidate, control_name='mentor_guard_select_apprentice')
            if not self._wait(m, lambda frame: detect(frame, 'guard_invite_title')
                              and _selected(frame, candidate), timeout=5):
                return False

            def send():
                frame = self._capture(m)
                if not detect(frame, 'guard_invite_title') or not _selected(frame, candidate):
                    return False
                m.click(773, 574, control_name='mentor_guard_send')
                return True

            if not invite_guard_with_listener(self.apprentice, send, timeout=15):
                return False
            completed = lock_guard_lineups(m, self.apprentice, self._both_confirmed, timeout=15)
            return completed
        finally:
            if not completed and not self._leave_room():
                raise RuntimeError('守护历练未能确认退出房间，请立即检查师父画面')

    def start(self):
        """Start only after a fresh two-device identity and lineup check."""
        m = self._capture(self.mentor)
        a = self._capture(self.apprentice)
        if not (detect(m, 'guard_challenge') and detect(m, 'guard_room')
                and detect(a, 'guard_room') and self._both_confirmed(m, a)
                and lineup_state(m) == lineup_state(a) == 'lock'):
            if not self._leave_room():
                raise RuntimeError('守护历练开战校验失败，且未能确认退出房间')
            return False
        self.mentor.click(1215, 642, control_name='mentor_guard_challenge')
        # Do not count the round as complete here: both battle and result must
        # be positively verified by the caller.
        for device in (self.mentor, self.apprentice):
            if not self._wait(device, lambda frame: (
                    GeneralBattleAssets.I_PREPARE_HIGHLIGHT.match(frame)
                    or GeneralBattleAssets.I_EXIT.match(frame)
                    or GeneralBattleAssets.I_WIN.match(frame)), timeout=20):
                return False
        return True
