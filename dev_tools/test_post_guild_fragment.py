"""Offline checks for the fragment modal; no device actions."""
import unittest
from unittest.mock import Mock, patch
from tasks.GroupedAwakening.post_guild import dismiss_received_fragment, collective_missions_visible, open_collective_missions, open_awake_material, read_material_selection
from module.exception import GameStuckError


class FragmentModalTests(unittest.TestCase):
    def test_material_open_waits_when_banner_covers_open_modal(self):
        task = Mock()
        with patch('tasks.GroupedAwakening.post_guild.material_selection', side_effect=[None, 0]), patch('tasks.GroupedAwakening.post_guild.time.sleep'):
            open_awake_material(task)
        task.device.click.assert_not_called()

    def test_material_open_retries_only_verified_high_grade_mission(self):
        task = Mock()
        task.appear.return_value = False
        with patch('tasks.GroupedAwakening.post_guild.material_selection', side_effect=[None, 0]), patch('tasks.GroupedAwakening.post_guild.collective_missions_visible', return_value=True), patch('tasks.GroupedAwakening.post_guild._words', return_value='提交高级觉醒材料1个'), patch('tasks.GroupedAwakening.post_guild.time.sleep'):
            open_awake_material(task)
        task.device.click.assert_called_once_with(300,492,control_name='open_awake_material')

    def test_unreadable_material_count_stops_without_clicking(self):
        task = Mock()
        with patch('tasks.GroupedAwakening.post_guild.time.monotonic', side_effect=[0,0,20]), patch('tasks.GroupedAwakening.post_guild.material_selection', return_value=None), patch('tasks.GroupedAwakening.post_guild.time.sleep'):
            with self.assertRaises(GameStuckError):
                read_material_selection(task)
        task.device.click.assert_not_called()

    def test_entry_accepts_verified_missions_with_covered_title_without_clicking(self):
        task = Mock()
        with patch('tasks.GroupedAwakening.post_guild.collective_missions_visible', return_value=True):
            open_collective_missions(task)
        task.screenshot.assert_called_once()
        task.appear_then_click.assert_not_called()

    def test_missions_with_covered_title_require_footer_and_records(self):
        task = Mock()
        for records in (True, False):
            task.appear.return_value = records
            with patch('tasks.GroupedAwakening.post_guild._words',
                       side_effect=['欢迎进入游戏', '双倍奖励10/10今日已完成次数30/30']):
                self.assertEqual(collective_missions_visible(task), records)
        with patch('tasks.GroupedAwakening.post_guild._words',
                   side_effect=['欢迎进入游戏', '今日已完成次数30/30']):
            self.assertFalse(collective_missions_visible(task))

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
