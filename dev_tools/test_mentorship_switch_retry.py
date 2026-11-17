import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameStuckError, GameSessionExpiredError
from tasks.Mentorship.script_task import ScriptTask


class SwitchRetryTests(unittest.TestCase):
    def run_switch(self, results):
        task = SimpleNamespace(read_identity=Mock())
        device = Mock()
        player = Mock()
        account = object()
        with patch('tasks.Mentorship.script_task.FindJade.switch_support_account',
                   side_effect=results) as switch:
            result = ScriptTask.switch_apprentice(task, player, device, account)
        return result, task, switch

    def test_login_timeout_retries_after_client_recovery(self):
        result, task, switch = self.run_switch([GameStuckError('Wait too long'), True])
        self.assertTrue(result)
        self.assertEqual(switch.call_count, 2)
        self.assertEqual(task.read_identity.call_count, 1)

    def test_session_expiry_retries(self):
        result, task, switch = self.run_switch([GameSessionExpiredError('expired'), True])
        self.assertTrue(result)
        self.assertEqual(switch.call_count, 2)

    def test_failed_switch_is_bounded(self):
        result, task, switch = self.run_switch([False, False, False])
        self.assertFalse(result)
        self.assertEqual(switch.call_count, 3)
        self.assertEqual(task.read_identity.call_count, 2)

    def test_success_has_no_recovery(self):
        result, task, switch = self.run_switch([True])
        self.assertTrue(result)
        task.read_identity.assert_not_called()


if __name__ == '__main__':
    unittest.main()
