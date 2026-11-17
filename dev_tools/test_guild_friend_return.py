"""Offline checks: a return timeout must not count as courtyard confirmation."""
import unittest
from unittest.mock import Mock, patch

from module.exception import GameStuckError, TaskEnd
from tasks.GameUi.page import page_main
from tasks.GuildQuickParticipation.script_task import return_after_friend_actions


class FriendReturnTests(unittest.TestCase):
    def test_confirmed_recovery_updates_caller_page(self):
        task = Mock()
        recovery = Mock()

        def verified():
            recovery.ui_current = page_main
            raise TaskEnd('Goto main verified')

        recovery.run.side_effect = verified
        with patch('tasks.GuildQuickParticipation.script_task.GotoMainTask', return_value=recovery):
            return_after_friend_actions(task)
        self.assertIs(task.ui_current, page_main)

    def test_unconfirmed_task_end_does_not_count_as_success(self):
        task = Mock()
        recovery = Mock(ui_current=page_main)
        recovery.run.side_effect = TaskEnd('Goto main unconfirmed')
        with patch('tasks.GuildQuickParticipation.script_task.GotoMainTask', return_value=recovery):
            with self.assertRaises(GameStuckError):
                return_after_friend_actions(task)
        self.assertIsNot(task.ui_current, page_main)

    def test_other_recovery_errors_propagate(self):
        task = Mock()
        recovery = Mock()
        recovery.run.side_effect = RuntimeError('device unavailable')
        with patch('tasks.GuildQuickParticipation.script_task.GotoMainTask', return_value=recovery):
            with self.assertRaisesRegex(RuntimeError, 'device unavailable'):
                return_after_friend_actions(task)


if __name__ == '__main__':
    unittest.main()
