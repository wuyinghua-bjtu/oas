import unittest
import numpy as np
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameStuckError
from tasks.WantedQuests.script_task import ScriptTask


class WantedSidebarTests(unittest.TestCase):
    def make_task(self, texts):
        task = SimpleNamespace(
            device=SimpleNamespace(image=None, save_screenshot=Mock()),
            screenshot=Mock(), appear=Mock(return_value=False),
            I_WQ_BOX='reward', I_TREASURE_BOX_CLICK='treasure',
            ui_page_appear=Mock(return_value=True), pre_work=Mock(return_value=True),
            O_WQ_WANTED=SimpleNamespace(detect_and_ocr=Mock(side_effect=[
                [SimpleNamespace(ocr_text=text) for text in frame] for frame in texts])))
        return task

    def test_collapsed_sidebar_is_not_completion(self):
        task = self.make_task([['真八岐大蛇']] * 4)
        with patch('tasks.WantedQuests.script_task.sleep'):
            with self.assertRaises(GameStuckError):
                ScriptTask.is_wq_remained(task)
        task.pre_work.assert_called_once()

    def test_retracing_recovers_pending_bounty(self):
        task = self.make_task([[], [], [], ['悬赏封印', '0/12']])
        with patch('tasks.WantedQuests.script_task.sleep'):
            self.assertTrue(ScriptTask.is_wq_remained(task))

    def test_verified_sealed_board_allows_completion(self):
        task = self.make_task([[], [], []])
        def verify_board():
            task._wanted_board_complete = True
            return True
        task.pre_work.side_effect = verify_board
        with patch('tasks.WantedQuests.script_task.sleep'):
            self.assertFalse(ScriptTask.is_wq_remained(task))

    def test_visible_bounty_needs_no_retrace(self):
        task = self.make_task([['悬赏封印', '0/12']])
        self.assertTrue(ScriptTask.is_wq_remained(task))
        task.pre_work.assert_not_called()

    def test_unverified_world_must_not_retrace(self):
        task = self.make_task([[], [], []])
        task.ui_page_appear.return_value = False
        with patch('tasks.WantedQuests.script_task.sleep'):
            with self.assertRaises(GameStuckError):
                ScriptTask.is_wq_remained(task)
        task.pre_work.assert_not_called()

    def test_open_board_must_not_run_courtyard_additional_click(self):
        task = SimpleNamespace(screenshot=Mock(), device=SimpleNamespace(image=None),
                               ui_get_current_page=Mock(), ui_goto=Mock(return_value=True),
                               ui_reward_appear_click=Mock(return_value=False),
                               ui_click_until_disappear=Mock(), need_invite_vip=Mock())
        for name in ('I_TRACE_DISABLE', 'I_TRACE_DISABLE_CURRENT', 'I_TRACE_ENABLE',
                     'I_TRACE_ENABLE_CURRENT', 'I_DETAIL_TRACED_CURRENT', 'I_WQ_INVITE_1',
                     'I_WQ_INVITE_2', 'I_WQ_INVITE_3', 'I_UI_BACK_RED'):
            setattr(task, name, name)
        task.appear = Mock(side_effect=lambda asset: asset == 'I_TRACE_DISABLE_CURRENT')
        with patch('tasks.WantedQuests.script_task.completed_reward_button', return_value=None):
            self.assertTrue(ScriptTask.pre_work(task))
        task.ui_get_current_page.assert_not_called()

    def test_unavailable_row_does_not_hide_next_bounty(self):
        rows = [SimpleNamespace(ocr_text='0/12', box=np.array([[20, 190], [60, 190], [60, 210], [20, 210]])),
                SimpleNamespace(ocr_text='0/10', box=np.array([[20, 290], [60, 290], [60, 310], [20, 310]]))]
        task = SimpleNamespace(O_WQ_TEXT_ALL=SimpleNamespace(
            roi=(12, 119, 88, 393), detect_and_ocr=Mock(return_value=rows)),
            _wanted_blocked_rows=[319])
        result = ScriptTask.find_wq(task, None)
        self.assertEqual(result[:3], (0, 1, 10))

    def test_only_blocked_rows_returns_failure(self):
        task = SimpleNamespace(screenshot=Mock(), O_WQ_NUMBER=SimpleNamespace(ocr=Mock(return_value=0)),
                               device=SimpleNamespace(image=None), is_wq_remained=Mock(return_value=True),
                               appear=Mock(return_value=False), I_WQ_BOX='reward',
                               I_TREASURE_BOX_CLICK='treasure', current_count=0,
                               O_WQ_TEXT_ALL=SimpleNamespace(),
                               find_wq=Mock(side_effect=[(0,1,12,[35,308,42,17]),(-2,-2,-2,[0,0,0,0])]),
                               execute_mission=Mock(return_value=False), ui_click_until_disappear=Mock(),
                               I_UI_BACK_RED='back', ui_get_current_page=Mock(), ui_goto=Mock(return_value=True))
        with patch('tasks.WantedQuests.script_task.sleep'):
            self.assertFalse(ScriptTask.complete_traced_quests(task))


if __name__ == '__main__':
    unittest.main()
