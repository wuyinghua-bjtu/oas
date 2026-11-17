import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.GuildQuickParticipation import kirin
from tasks.FindJade import WantedQuestsEx as sender
from tasks.WantedQuests.config import CooperationType


class GuildEntryTests(unittest.TestCase):
    def test_observed_board_ocr_overrides_false_legacy_match(self):
        task = SimpleNamespace(appear=Mock(return_value=True),
                               device=SimpleNamespace(click=Mock()))
        for label in ('狩猎战', '柠猎战'):
            with self.subTest(label=label), patch.object(kirin, '_words',
                    side_effect=lambda task, box: '集体任务' if box[1] == 150 else label):
                self.assertTrue(kirin.open_hunt_entry(task))
                task.device.click.assert_called_with(260,500,control_name='guild_open_hunting_board')

    def test_unknown_board_does_not_click_legacy_false_match(self):
        task = SimpleNamespace(appear=Mock(return_value=True),
                               device=SimpleNamespace(click=Mock()))
        with patch.object(kirin, '_words',
                side_effect=lambda task, box: '集体任务' if box[1] == 150 else ''):
            self.assertFalse(kirin.open_hunt_entry(task))
        task.device.click.assert_not_called()

    def test_legacy_layout_still_uses_legacy_entry(self):
        task = SimpleNamespace(appear=Mock(return_value=True),
                               device=SimpleNamespace(click=Mock()))
        with patch.object(kirin, '_words', return_value=''):
            self.assertTrue(kirin.open_hunt_entry(task))
        task.device.click.assert_called_once_with(210,295,control_name='guild_open_hunting')


class RoomLoadingTests(unittest.TestCase):
    def task(self):
        return SimpleNamespace(screenshot=Mock(), appear=Mock(return_value=False),
            appear_then_click=Mock(return_value=False), I_CREATE_ROOM='room',
            I_CREATE_ENSURE='confirm', I_CREATE_ENSURE_2='confirm2')

    def test_temporarily_missing_create_button_waits_for_dialog(self):
        task = self.task()
        task.appear.side_effect = lambda marker: marker == 'confirm' and task.screenshot.call_count >= 3
        with patch('tasks.Component.GeneralRoom.general_room.time.sleep'):
            self.assertTrue(GeneralRoom.create_room(task))
        self.assertEqual(task.screenshot.call_count, 3)

    def test_missing_dialog_has_finite_deadline(self):
        task = self.task()
        with patch('tasks.Component.GeneralRoom.general_room.time.monotonic',
                   side_effect=[0,1,21]), patch('tasks.Component.GeneralRoom.general_room.time.sleep'):
            self.assertFalse(GeneralRoom.create_room(task))
        self.assertEqual(task.screenshot.call_count, 1)


class SenderBoardTests(unittest.TestCase):
    def test_routes_are_read_after_opening_pending_card(self):
        device = SimpleNamespace(image='frame', click=Mock())
        task = SimpleNamespace(device=device, screenshot=Mock(),
            ui_click_until_disappear=Mock(), I_UI_BACK_RED='back',
            enter_sender_exploration=Mock(), sender_tracker_visible=Mock(return_value=False),
            open_cooperation_board=Mock(return_value=True),
            read_cooperation_info=Mock(side_effect=[[
                {'already_shared':True, 'completed':False, 'type':CooperationType.Jade,
                 'inviteBtn':SimpleNamespace(roi_front=(316,401,34,34)), 'slot':1}], []]),
            black_gold_skin=True, sender_challenge_tickets=Mock(return_value=1),
            I_TRACE_ENABLE='board', I_TRACE_DISABLE='board2',
            sender_routes=Mock(return_value=[(0,'第七章',7,'go','探索')]), explore=Mock(),
            challenge=Mock(), secret=Mock(), sender_soul=Mock())
        for n in range(1,5):
            setattr(task, f'I_GOTO_{n}', f'go{n}')
        task.appear = Mock(side_effect=lambda marker: marker == 'board' or
                           (marker.startswith('go') and bool(device.click.call_count)))
        with patch.object(sender,'sleep'):
            sender.finish_sender_cooperation(task)
        device.click.assert_called_once_with(220,230,control_name='findjade_sender_detail')
        task.sender_routes.assert_called_once_with('frame',1)
        task.explore.assert_called_once_with('go',1)

    def test_ambiguous_pending_cards_stop_before_any_click(self):
        task = SimpleNamespace(device=SimpleNamespace(click=Mock()),
            ui_click_until_disappear=Mock(), I_UI_BACK_RED='back',
            enter_sender_exploration=Mock(), sender_tracker_visible=Mock(return_value=False),
            open_cooperation_board=Mock(return_value=True),
            read_cooperation_info=Mock(return_value=[
                {'already_shared':True,'completed':False,'type':CooperationType.Jade},
                {'already_shared':True,'completed':False,'type':CooperationType.Jade}]))
        with self.assertRaisesRegex(sender.GameStuckError,'uniquely select'):
            sender.finish_sender_cooperation(task)
        task.device.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
