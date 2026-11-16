"""Invitation loading regression tests without devices or OCR inference."""
import unittest
from unittest.mock import Mock, patch

from tasks.TripleAwakening.script_task import Participant, EvoTask
from tasks.Component.GeneralInvite.config_invite import FindMode


class InviteLoadingTests(unittest.TestCase):
    def task(self):
        task = Participant.__new__(Participant)
        task.device = Mock()
        task.screenshot = Mock()
        task.appear = Mock()
        task.appear_then_click = Mock(return_value=True)
        for name in ('I_INVITE_ENSURE', 'I_LOAD_FRIEND', 'I_ADD_1', 'I_ADD_2'):
            setattr(task, name, object())
        for name in ('O_F_LIST_1', 'O_F_LIST_2', 'O_F_LIST_3', 'O_F_LIST_4'):
            setattr(task, name, Mock())
        return task

    @patch('tasks.TripleAwakening.script_task.time.sleep')
    @patch.object(EvoTask, 'invite_friend', return_value=True)
    def test_waits_for_loaded_labels_and_clicks_only_one_add(self, parent, sleep):
        task = self.task()
        frames = iter(('room', 'empty', 'ready'))
        state = {}
        def screenshot():
            state['frame'] = next(frames)
        task.screenshot.side_effect = screenshot
        task.appear.side_effect = lambda rule: (
            rule is task.I_INVITE_ENSURE and state['frame'] != 'room')
        for name in ('O_F_LIST_1', 'O_F_LIST_2', 'O_F_LIST_3', 'O_F_LIST_4'):
            getattr(task, name).ocr.side_effect = lambda image: (
                '好友' if state['frame'] == 'ready' else None)
        self.assertTrue(task.invite_friend('test002'))
        self.assertEqual(task.screenshot.call_count, 3)
        task.appear_then_click.assert_called_once_with(task.I_ADD_2, interval=2)
        parent.assert_called_once_with('test002', FindMode.AUTO_FIND)

    @patch.object(EvoTask, 'invite_friend', return_value=False)
    def test_preserves_recent_friend_mode_and_parent_result(self, parent):
        task = self.task()
        task.appear.side_effect = lambda rule: rule is task.I_INVITE_ENSURE
        for name in ('O_F_LIST_1', 'O_F_LIST_2', 'O_F_LIST_3', 'O_F_LIST_4'):
            getattr(task, name).ocr.return_value = '最近'
        self.assertFalse(task.invite_friend('test002', FindMode.RECENT_FRIEND))
        parent.assert_called_once_with('test002', FindMode.RECENT_FRIEND)
        task.appear_then_click.assert_not_called()
