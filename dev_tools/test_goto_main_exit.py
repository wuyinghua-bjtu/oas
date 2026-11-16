"""Dialog recovery tests without a live device."""
import unittest
from unittest.mock import Mock, patch
from tasks.GotoMain.script_task import ScriptTask


class ExitDialogTests(unittest.TestCase):
    def check_dialog(self, prompt, selected):
        task = ScriptTask.__new__(ScriptTask)
        task.device = Mock()
        rows = [Mock(ocr_text=text, box=((0, 0), (20, 0), (20, 20), (0, 20)))
                for text in (prompt, '取消', '确定')]
        with patch('tasks.GotoMain.script_task.RuleOcr') as reader:
            reader.return_value.detect_and_ocr.return_value = rows
            self.assertEqual(task._cancel_exit_dialog(), selected is not None)
        if selected:
            task.device.click.assert_called_once_with(360, 240, control_name=selected)
        else:
            task.device.click.assert_not_called()

    def test_team_exit_is_confirmed(self):
        self.check_dialog('确认退出组队面板吗？', 'GOTO_MAIN_CONFIRM_LEAVE_TEAM')

    def test_game_exit_is_cancelled(self):
        self.check_dialog('确认退出游戏吗？', 'GOTO_MAIN_CANCEL_EXIT')

    def test_unrelated_confirmation_is_untouched(self):
        self.check_dialog('确认购买吗？', None)
