import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2

from tasks.WantedQuests.board_state import sealed_page_has_next
from tasks.WantedQuests.script_task import ScriptTask


class WantedBoardStateTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / 'fixtures' / 'wanted_quests' / 'sealed_page_with_next.png'
        self.image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)

    def test_recorded_sealed_page_has_next(self):
        self.assertTrue(sealed_page_has_next(self.image))

    def test_one_unverified_card_must_not_turn(self):
        self.image[240:450, 455:555] = 0
        self.assertFalse(sealed_page_has_next(self.image))

    def test_missing_arrow_or_board_title_must_not_turn(self):
        without_arrow = self.image.copy()
        without_arrow[330:410, 1160:1260] = 0
        self.assertFalse(sealed_page_has_next(without_arrow))
        self.image[20:90, 545:735] = 0
        self.assertFalse(sealed_page_has_next(self.image))

    def test_invalid_frame(self):
        self.assertFalse(sealed_page_has_next(None))

    def test_sealed_page_is_turned_before_trace(self):
        device = SimpleNamespace(image=self.image, click=Mock())
        task = SimpleNamespace(device=device, special_main=False,
                               ui_get_current_page=Mock(), ui_goto=Mock(), screenshot=Mock(),
                               appear_then_click=Mock(return_value=False),
                               appear_then_click_multi_scale=Mock(return_value=False),
                               ui_click_until_disappear=Mock())
        for name in ('I_TRACE_DISABLE', 'I_TRACE_DISABLE_CURRENT', 'I_WQ_SEAL', 'I_WQ_DONE',
                     'I_TRACE_ENABLE', 'I_TRACE_ENABLE_CURRENT', 'I_UI_BACK_RED',
                     'I_WQ_INVITE_1', 'I_WQ_INVITE_2', 'I_WQ_INVITE_3'):
            setattr(task, name, name)
        task.appear = Mock(side_effect=lambda asset: asset == 'I_TRACE_DISABLE' and device.click.called)
        with patch('tasks.WantedQuests.script_task.sleep'):
            self.assertTrue(ScriptTask.pre_work(task))
        device.click.assert_called_once_with(1215, 372, control_name='wanted_board_next_page')


if __name__ == '__main__':
    unittest.main()
