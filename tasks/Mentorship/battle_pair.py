"""Bounded two-device battle handling for the mentorship task."""
from module.config.local_values import local_text
import time
from dataclasses import dataclass

from tasks.Component.GeneralBattle.assets import GeneralBattleAssets as Battle
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite
from tasks.GameUi.assets import GameUiAssets as Game
from tasks.ExperienceYoukai.assets import ExperienceYoukaiAssets as Experience
from tasks.GoldYoukai.assets import GoldYoukaiAssets as Gold
from module.atom.ocr import RuleOcr
from .vision import detect


def clear_verified_statistics(device, apprentice_name, timeout=12):
    """Dismiss a finished pair's statistics after an interrupted controller."""
    footer = RuleOcr(roi=(470, 665, 350, 50), area=(470, 665, 350, 50),
                     mode='Full', method='Default', keyword='', name='mentorship_result_continue')
    names = RuleOcr(roi=(300, 180, 215, 180), area=(300, 180, 215, 180),
                    mode='Full', method='Default', keyword='', name='mentorship_result_names')
    deadline = time.monotonic() + timeout
    handled = False
    last_click = 0
    while time.monotonic() < deadline:
        device.screenshot()
        frame = device.image
        if not (Experience.I_EXP_WIN.match(frame) or Gold.I_GOLD_WIN.match(frame)):
            return handled
        words = ''.join(x.ocr_text for x in footer.detect_and_ocr(frame)).replace(' ', '')
        identities = ''.join(x.ocr_text for x in names.detect_and_ocr(frame)).replace(' ', '')
        if '点击空白区域继续' not in words or local_text('LOCAL_SUPPORT_') not in identities or apprentice_name not in identities:
            raise RuntimeError('师徒结算页身份或继续提示未确认')
        if time.monotonic() - last_click >= 1.5:
            device.click(640, 695, control_name='mentorship_resume_statistics')
            handled = True
            last_click = time.monotonic()
        time.sleep(.3)
    raise RuntimeError('师徒结算页未关闭')


@dataclass
class _Side:
    device: object
    ready_clicked: bool = False
    exit_confirm_clicked: bool = False
    exited: bool = False
    win_seen: bool = False
    returned: bool = False
    last_action: float = 0


class PairBattle:
    """Observe both devices until each has a verified terminal state."""

    def __init__(self, mentor, apprentice):
        self.mentor = _Side(mentor)
        self.apprentice = _Side(apprentice)

    @staticmethod
    def _click(side, x, y, name, interval=.8):
        now = time.monotonic()
        if now - side.last_action < interval:
            return False
        side.device.click(x, y, control_name=name)
        side.last_action = now
        return True

    def _advance(self, side, stone_leader=False, guardian=False):
        side.device.screenshot()
        frame = side.device.image
        if side.returned:
            return True
        if guardian and side.win_seen and detect(frame, 'guard_continue_prompt'):
            self._click(side, 525, 438, 'mentorship_guard_return')
            return False
        if guardian and side.win_seen and detect(frame, 'guard_entry'):
            side.returned = True
            return True
        if Battle.I_FALSE.match(frame):
            raise RuntimeError('师徒副本战斗失败')
        if stone_leader and side.ready_clicked and not side.exited:
            if Battle.I_EXIT_ENSURE.match(frame):
                if self._click(side, 755, 438, 'mentor_stone_exit_confirm'):
                    side.exit_confirm_clicked = True
                return False
            if Battle.I_EXIT.match(frame) and not Battle.I_PREPARE_HIGHLIGHT.match(frame):
                self._click(side, 37, 33, 'mentor_stone_exit')
                return False
            if side.exit_confirm_clicked and (Game.I_CHECK_MAIN.match(frame) or Game.I_CHECK_TEAM.match(frame)):
                side.exited = side.returned = True
                return True
        if Battle.I_PREPARE_HIGHLIGHT.match(frame):
            if self._click(side, 1180, 590, 'mentorship_prepare'):
                side.ready_clicked = True
            return False
        gold_win = Gold.I_GOLD_WIN.match(frame)
        if (gold_win or Battle.I_WIN.match(frame) or Battle.I_DE_WIN.match(frame)
                or Experience.I_EXP_WIN.match(frame)):
            side.win_seen = True
            # The gold statistics panel covers the old (1060, 560) target.
            # Its explicit continue area is along the bottom of the screen.
            x, y = (640, 695) if gold_win else (1060, 560)
            self._click(side, x, y, 'mentorship_victory', interval=1.5)
            return False
        if (Battle.I_REWARD.match(frame) or Battle.I_REWARD_GOLD.match(frame)
                or Battle.I_REWARD_STATISTICS.match(frame)):
            if side.win_seen:
                self._click(side, 1060, 560, 'mentorship_reward')
            return False
        if side.win_seen and not (guardian and side is self.mentor) and (Game.I_CHECK_MAIN.match(frame) or Game.I_CHECK_TEAM.match(frame) or Game.I_CHECK_EXPLORATION.match(frame)
                              or (not guardian and Invite.I_GI_SURE.match(frame))):
            side.returned = True
            return True
        return False

    def run(self, stone_leader_exit=False, timeout=480, guardian=False):
        deadline = time.monotonic() + timeout
        devices = (self.mentor.device, self.apprentice.device)
        for device in devices:
            device.click_record_clear()
            device.stuck_record_add('BATTLE_STATUS_S')
        try:
            while time.monotonic() < deadline:
                self._advance(self.mentor, stone_leader_exit, guardian)
                self._advance(self.apprentice, guardian=guardian)
                if self.mentor.returned and self.apprentice.returned:
                    return True
                time.sleep(.2)
            return False
        finally:
            for device in devices:
                device.stuck_record_clear()
