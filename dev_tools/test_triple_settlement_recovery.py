"""Offline regressions for skipped leader victory animations."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.TripleAwakening.script_task import ScriptTask


class SettlementRecoveryTests(unittest.TestCase):
    def player(self, frames):
        p = Mock()
        p.device.config.script.device.handle = 'leader'
        states = iter(frames)
        p.state = None
        def screenshot():
            p.state = next(states)
        p.screenshot.side_effect = screenshot
        p.failure_visible.return_value = False
        p.handle_soul_mismatch_dialog.return_value = False
        p.appear_then_click.return_value = False
        p.is_in_room.return_value = False
        p.appear.side_effect = lambda rule: p.state == 'reward' and rule is p.I_REWARD
        return p

    def run_battle(self, leader, record):
        teammates = [Mock(), Mock()]
        for p, name in zip(teammates, ('member1', 'member2')):
            p.device.config.script.device.handle = name
        with patch('tasks.TripleAwakening.script_task.RuleOcr') as ocr, patch('tasks.TripleAwakening.script_task.time.sleep'):
            ocr.return_value.detect_and_ocr.side_effect = lambda image: [SimpleNamespace(ocr_text='是否邀请队友继续进行战斗？')] if leader.state == 'prompt' else []
            ScriptTask.battle([leader] + teammates, False, record, Mock())
        return teammates

    def record(self):
        return {'completed': 0, 'pending_round': {'round': 1,
                'won': {'leader': False, 'member1': True, 'member2': True},
                'settled': {'leader': False, 'member1': True, 'member2': True}}}

    def test_reward_confirms_win_when_animation_was_missed(self):
        leader = self.player(['reward', 'prompt'])
        record = self.record()
        self.run_battle(leader, record)
        self.assertTrue(record['pending_round']['won']['leader'])
        self.assertTrue(record['pending_round']['settled']['leader'])
        leader.click.assert_called_once_with(leader.C_REWARD_1, interval=1)

    def test_resume_prompt_with_two_settled_winners(self):
        leader = self.player(['prompt'])
        record = self.record()
        teammates = self.run_battle(leader, record)
        self.assertTrue(record['pending_round']['settled']['leader'])
        for p in teammates:
            p.screenshot.assert_not_called()

    def test_unknown_frame_does_not_credit_leader(self):
        leader = self.player(['unknown'])
        record = self.record()
        with self.assertRaises(StopIteration):
            self.run_battle(leader, record)
        self.assertFalse(record['pending_round']['won']['leader'])
        leader.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
