"""Offline checks for the fragment modal; no device actions."""
import unittest
from unittest.mock import Mock, patch
from tasks.GroupedAwakening.post_guild import dismiss_received_fragment


class FragmentModalTests(unittest.TestCase):
    def test_closes_confirmed_fragment_modal(self):
        task = Mock()
        with patch('tasks.GroupedAwakening.post_guild._words',
                   side_effect=['已收到碎片1个', '感谢']):
            self.assertTrue(dismiss_received_fragment(task))
        task.device.click.assert_called_once_with(
            865, 165, control_name='post_close_received_fragment')

    def test_does_not_click_other_pages_or_incomplete_modal(self):
        for labels in (['集体任务'], ['已收到碎片1个', '领取奖励']):
            task = Mock()
            with patch('tasks.GroupedAwakening.post_guild._words', side_effect=labels):
                self.assertFalse(dismiss_received_fragment(task))
            task.device.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
