import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameStuckError
from tasks.Component.GeneralBattle.general_battle import GeneralBattle


class BattlePreparationTests(unittest.TestCase):
    def battle(self):
        battle = object.__new__(GeneralBattle)
        battle.current_count = 0
        battle.screenshot = Mock()
        return battle

    def test_confirmation_does_not_disable_reminder(self):
        battle = self.battle()
        battle.appear = Mock(return_value=True)
        battle.appear_then_click = Mock(return_value=False)
        self.assertTrue(battle.handle_soul_mismatch_dialog())
        battle.appear_then_click.assert_called_once_with(
            battle.I_CONFIRM_CLOSE_DIFF_SOUL, interval=0.8)

    def test_wanted_non_secret_battle_uses_common_auto_mode_controller(self):
        from tasks.WantedQuests.script_task import ScriptTask as WantedTask
        task = object.__new__(WantedTask)
        task._wanted_secret_battle = False
        with patch.object(GeneralBattle, 'battle_wait', return_value=True) as common, \
                patch('tasks.Secret.script_task.ScriptTask.battle_wait',
                      side_effect=AssertionError('Wrong secret battle controller')):
            self.assertTrue(task.battle_wait(False))
        common.assert_called_once_with(task, False)

    def test_failed_preparation_never_enters_battle_wait(self):
        battle = self.battle()
        battle.battle_before = Mock(return_value=False)
        battle.battle_wait = Mock()
        with self.assertRaises(GameStuckError):
            battle.run_general_battle(SimpleNamespace())
        battle.battle_wait.assert_not_called()

    def test_popup_handled_before_real_battle_detection(self):
        battle = self.battle()
        battle.handle_soul_mismatch_dialog = Mock(side_effect=[True, False])
        battle.is_in_real_battle = Mock(return_value=True)
        with patch('tasks.Component.GeneralBattle.general_battle.Timer') as timer:
            timer.return_value.start.return_value.reached.return_value = False
            self.assertTrue(battle.battle_before(None, SimpleNamespace()))
        self.assertEqual(battle.screenshot.call_count, 2)
        battle.is_in_real_battle.assert_called_once_with(False)

    def test_late_popup_timeout_never_runs_mode_ocr(self):
        battle = self.battle()
        battle.device = Mock()
        battle.handle_soul_mismatch_dialog = Mock(return_value=True)
        battle.ocr_appear = Mock()
        with patch('tasks.Component.GeneralBattle.general_battle.Timer') as timer:
            timer.return_value.start.return_value.reached.return_value = True
            with self.assertRaises(GameStuckError):
                battle.battle_wait(False)
        battle.ocr_appear.assert_not_called()


if __name__ == '__main__':
    unittest.main()
