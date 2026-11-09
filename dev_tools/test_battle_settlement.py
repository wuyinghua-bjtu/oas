"""Offline coverage for the September 6 guild-raid reward-page stall."""

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from module.atom.image import RuleImage
from module.exception import GameStuckError
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.RyouToppa.script_task import ScriptTask


FIXTURES = Path(__file__).parent / 'fixtures'
MODULE = 'tasks.Component.GeneralBattle.general_battle'


class BattleSettlementTests(unittest.TestCase):
    def frame(self, filename):
        with Image.open(FIXTURES / filename) as image:
            return np.array(image.convert('RGB'))

    def reward_rule(self, roi_back=None):
        source = GeneralBattle.I_REWARD
        return RuleImage((547, 518, 172, 96),
                         source.roi_back if roi_back is None else roi_back,
                         source.method, source.threshold, source.file)

    def battle(self, frames):
        battle = object.__new__(ScriptTask)
        battle.device = Mock()
        battle._frame = None
        sequence = iter(frames)

        def screenshot():
            try:
                battle._frame = next(sequence)
            except StopIteration as exc:
                raise AssertionError('Settlement failed to finish within supplied frames') from exc

        battle.screenshot = Mock(side_effect=screenshot)
        states = {'win': battle.I_WIN, 'loss': battle.I_FALSE,
                  'reward': battle.I_REWARD}
        battle.appear = Mock(side_effect=lambda asset, **kwargs:
                             asset == states.get(battle._frame))
        battle.click = Mock(return_value=True)
        battle.battle_settlement_return_visible = Mock(
            side_effect=lambda: battle._frame == 'board')
        return battle

    def finish(self, battle, win=True, expiry=None):
        with patch(MODULE + '.Timer') as timer, patch(MODULE + '.sleep'):
            deadline = timer.return_value.start.return_value
            deadline.reached = Mock(return_value=False, side_effect=expiry)
            return battle.finish_battle_settlement(win)

    def test_real_reward_frame_reproduces_old_crop_and_matches_fixed_roi(self):
        frame = self.frame('battle_reward_shifted_091003.png')
        self.assertFalse(self.reward_rule((547, 518, 172, 96)).match(frame))
        fixed = self.reward_rule()
        self.assertTrue(fixed.match(frame))
        self.assertEqual(fixed.roi_front[:2], [583, 550])
        self.assertEqual(fixed.threshold, 0.8)

    def test_reward_rejects_unrelated_real_pages(self):
        for filename in ('remote_login_dialog.png', 'own_foster_active.png',
                         'activation_empty_gray.png', 'own_foster_friend_list.png'):
            with self.subTest(filename=filename):
                self.assertFalse(self.reward_rule().match(self.frame(filename)))
        self.assertFalse(self.reward_rule().match(np.zeros((720, 1280, 3), np.uint8)))

    def test_asset_generator_roi_and_threshold_stay_in_sync(self):
        records = json.loads(Path('tasks/Component/GeneralBattle/gb/image.json').read_text('utf-8'))
        record = next(item for item in records if item['imageName'] == 'gb_reward.png')
        self.assertEqual(tuple(map(int, record['roiBack'].split(','))), self.reward_rule().roi_back)
        self.assertEqual(record['threshold'], 0.8)

    def test_unknown_animation_between_reward_and_board_is_not_success(self):
        battle = self.battle(['win', 'unknown', 'reward', 'unknown', 'board', 'board'])
        self.assertTrue(self.finish(battle))
        self.assertEqual(battle.screenshot.call_count, 6)
        self.assertEqual(battle.click.call_count, 2)

    def test_return_page_must_appear_on_consecutive_frames(self):
        battle = self.battle(['reward', 'board', 'unknown', 'board', 'board'])
        self.assertTrue(self.finish(battle))
        self.assertEqual(battle.screenshot.call_count, 5)

    def test_loss_also_requires_confirmed_return_page(self):
        battle = self.battle(['loss', 'unknown', 'board', 'board'])
        self.assertFalse(self.finish(battle, win=False))
        self.assertEqual(battle.screenshot.call_count, 4)
        battle.click.assert_called_once_with(battle.I_FALSE, interval=1.5)

    def test_no_reward_battle_can_finish_with_positive_board_evidence(self):
        battle = self.battle(['unknown', 'board', 'board'])
        self.assertTrue(self.finish(battle))
        battle.click.assert_not_called()

    def test_unknown_page_times_out_with_evidence_and_never_clicks(self):
        battle = self.battle(['unknown'] * 3)
        with self.assertRaisesRegex(GameStuckError, 'settlement not confirmed'):
            self.finish(battle, expiry=[False, False, True])
        battle.click.assert_not_called()
        battle.device.save_screenshot.assert_called_once_with(
            genre='battle_settlement', interval=0)

    def test_ineffective_recognized_clicks_are_bounded_by_count_and_deadline(self):
        battle = self.battle(['reward'] * 13)
        with self.assertRaises(GameStuckError):
            self.finish(battle, expiry=[False] * 12 + [True])
        self.assertEqual(battle.click.call_count, 8)
        battle.battle_settlement_return_visible.assert_not_called()

    def test_throttled_click_is_not_evidence_of_result_disappearance(self):
        battle = self.battle(['reward', 'reward', 'board', 'board'])
        battle.click.return_value = False
        self.assertTrue(self.finish(battle))
        self.assertEqual(battle.screenshot.call_count, 4)
        self.assertEqual(battle.battle_settlement_return_visible.call_count, 2)

    def test_board_requires_independent_positive_markers(self):
        battle = object.__new__(ScriptTask)
        for visible in ([], [battle.I_TOPPA_RECORD], [battle.I_KEKKAI_TOPPA]):
            battle.appear = Mock(side_effect=lambda asset: asset in visible)
            self.assertFalse(battle.battle_settlement_return_visible())
        for second in (battle.I_KEKKAI_TOPPA, battle.I_RYOU_REWARD,
                       battle.I_RYOU_REWARD_90, battle.I_SUCCESS_PENETRATION):
            battle.appear = Mock(side_effect=lambda asset: asset in (battle.I_TOPPA_RECORD, second))
            self.assertTrue(battle.battle_settlement_return_visible())

    def test_guild_raid_battle_wait_uses_confirmed_settlement(self):
        battle = self.battle(['win'])
        battle.handle_soul_mismatch_dialog = Mock(return_value=False)
        battle.is_in_real_battle = Mock(return_value=False)
        battle.battle_result_visible = Mock(return_value=True)
        battle.finish_battle_settlement = Mock(return_value=True)
        self.assertTrue(battle.battle_wait(False))
        battle.finish_battle_settlement.assert_called_once_with(True)

    def test_other_tasks_do_not_gain_an_unverified_destination_requirement(self):
        self.assertFalse(object.__new__(GeneralBattle).battle_settlement_requires_confirmation())
        self.assertTrue(object.__new__(ScriptTask).battle_settlement_requires_confirmation())


if __name__ == '__main__':
    unittest.main()
