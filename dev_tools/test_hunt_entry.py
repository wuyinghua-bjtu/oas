import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.GuildQuickParticipation.kirin import GUILD_HUNT, open_hunt_entry, guild_activity_board


class HuntEntryTest(unittest.TestCase):
    def setUp(self):
        self.task = SimpleNamespace(device=SimpleNamespace(click=Mock()), appear=Mock())

    @patch('tasks.GuildQuickParticipation.kirin.guild_activity_board', return_value=True)
    def test_new_board_opens_without_legacy_sidebar(self, board):
        self.task.appear.return_value = False
        self.assertTrue(open_hunt_entry(self.task))
        self.task.device.click.assert_called_once_with(
            260, 500, control_name='guild_open_hunting_board')
        self.task.appear.assert_not_called()

    @patch('tasks.GuildQuickParticipation.kirin.guild_activity_board', return_value=False)
    def test_legacy_sidebar_still_opens(self, board):
        self.task.appear.return_value = True
        self.assertTrue(open_hunt_entry(self.task))
        self.task.appear.assert_called_once_with(GUILD_HUNT)
        self.task.device.click.assert_called_once_with(
            210, GUILD_HUNT.roi_front[1] + GUILD_HUNT.roi_front[3] // 2 + 30,
            control_name='guild_open_hunting')

    @patch('tasks.GuildQuickParticipation.kirin.guild_activity_board', return_value=False)
    def test_unknown_page_is_not_clicked(self, board):
        self.task.appear.return_value = False
        self.assertFalse(open_hunt_entry(self.task))
        self.task.device.click.assert_not_called()

    def test_hunt_reuses_shared_entry(self):
        source = Path(__file__).resolve().parents[1] / 'tasks/Hunt/script_task.py'
        tree = ast.parse(source.read_text(encoding='utf8'))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'open_hunt_entry']
        self.assertEqual(len(calls), 1)

    def test_weekend_board_is_recognized(self):
        for label in ('狩猎战', '阴界之门'):
            with self.subTest(label=label), patch(
                    'tasks.GuildQuickParticipation.kirin._words', side_effect=['集体任务', label]):
                self.assertTrue(guild_activity_board(self.task))

    def test_hunt_opens_guild_before_day_branch(self):
        source = Path(__file__).resolve().parents[1] / 'tasks/Hunt/script_task.py'
        tree = ast.parse(source.read_text(encoding='utf8'))
        run = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'run')
        navigation = next(node for node in run.body if isinstance(node, ast.Try))
        self.assertEqual(navigation.body[0].value.func.id, 'open_guild')


if __name__ == '__main__':
    unittest.main()
