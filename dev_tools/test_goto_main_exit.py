"""Dialog recovery tests without a live device."""
import unittest
from unittest.mock import Mock, patch
from tasks.GotoMain.script_task import ScriptTask


class ExitDialogTests(unittest.TestCase):
    def test_affairs_fallback_requires_both_task_labels_and_daily_control(self):
        from tasks.GuildQuickParticipation.courtyard import affairs_page_visible
        from tasks.Restart.login import LoginHandler
        for text, daily, expected in [('现世逢魔阴阳寮资金', True, True),
                                      ('现世逢魔', True, False),
                                      ('现世逢魔阴阳寮资金', False, False)]:
            task = Mock()
            task.appear.side_effect = lambda asset: daily if asset is LoginHandler.I_DAILY else False
            with patch('tasks.GuildQuickParticipation.courtyard.RuleOcr') as reader:
                reader.return_value.detect_and_ocr.return_value = [Mock(ocr_text=text)]
                self.assertEqual(affairs_page_visible(task), expected)

    def test_collective_missions_close_precedes_generic_back(self):
        from module.exception import TaskEnd
        task = ScriptTask.__new__(ScriptTask)
        task.device = Mock()
        task.screenshot = Mock()
        task._cancel_exit_dialog = Mock(return_value=False)
        task._main_menu_visible = Mock(side_effect=[False, True, True])
        task.appear_then_click = Mock()
        with patch('tasks.GroupedAwakening.post_guild.dismiss_received_fragment', return_value=False), patch('tasks.GroupedAwakening.post_guild.collective_missions_visible', return_value=True), patch('tasks.GotoMain.script_task.time.sleep'):
            with self.assertRaises(TaskEnd):
                task.run()
        task.device.click.assert_called_once_with(1168, 120, control_name='GOTO_MAIN_CLOSE_MISSIONS')
        task.appear_then_click.assert_not_called()
        task.device.adb_shell.assert_not_called()

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
