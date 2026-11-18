import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.GuildQuickParticipation.friend import find_main_friend


class FriendScrollTests(unittest.TestCase):
    def task(self):
        return SimpleNamespace(screenshot=Mock(), appear=Mock(return_value=False),
                               device=SimpleNamespace(image=None, swipe=Mock(), click=Mock()))

    def test_scrolls_until_exact_candidate(self):
        task = self.task()
        reader = Mock()
        reader.detect_and_ocr.return_value = [SimpleNamespace(ocr_text='其他好友')]
        with patch('tasks.GuildQuickParticipation.friend.monotonic', side_effect=range(100)), \
                patch('tasks.GuildQuickParticipation.friend.sleep'), \
                patch('tasks.GuildQuickParticipation.friend.RuleOcr', return_value=reader), \
                patch('tasks.GuildQuickParticipation.friend.name_candidates', side_effect=[[], [(300,400)]]):
            self.assertEqual(find_main_friend(task, object(), 25), [(300,400)])
        task.device.swipe.assert_called_once_with((350,420), (350,240), duration=.5,
                                                 control_name='guild_scroll_same_server_friends')
        task.device.click.assert_not_called()

    def test_stalled_list_stops_without_selecting_other_friend(self):
        task = self.task()
        reader = Mock()
        reader.detect_and_ocr.return_value = [SimpleNamespace(ocr_text='其他好友')]
        with patch('tasks.GuildQuickParticipation.friend.monotonic', side_effect=range(1000)), \
                patch('tasks.GuildQuickParticipation.friend.sleep'), \
                patch('tasks.GuildQuickParticipation.friend.RuleOcr', return_value=reader), \
                patch('tasks.GuildQuickParticipation.friend.name_candidates', return_value=[]):
            self.assertEqual(find_main_friend(task, object(), 200), [])
        self.assertEqual(task.device.swipe.call_count, 2)
        task.device.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
