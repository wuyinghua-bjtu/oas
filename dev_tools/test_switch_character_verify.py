import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameStuckError, RequestHumanTakeover
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.GameUi.page import page_login


MODULE = 'tasks.Component.SwitchAccount.switch_account'


class SwitchCharacterVerificationTests(unittest.TestCase):
    def task(self, character):
        task = object.__new__(SwitchAccount)
        task.to_account_info = SimpleNamespace(character=character, svr='test')
        task.config = Mock()
        task.device = Mock()
        task.ui_get_current_page = Mock(return_value=page_login)
        task.login = Mock(return_value=True)
        task.screenshot = Mock()
        return task

    def test_nickname_roi_excludes_badge_and_retains_numeric_suffix(self):
        for suffix in ('001', '005', '009'):
            character = '测试角色' + suffix
            with self.subTest(character=character):
                task = self.task(character)
                with patch(MODULE + '.LoginHandler'), patch(MODULE + '.RuleOcr') as ocr:
                    ocr.return_value.ocr.return_value = character
                    self.assertTrue(task.switchAccount(skip_harvest=True))
                    self.assertEqual(ocr.call_args.kwargs['roi'], (125, 25, 120, 32))
                    self.assertEqual(ocr.call_args.kwargs['area'], (125, 25, 120, 32))
                task.device.app_stop.assert_not_called()
                task.device.app_start.assert_not_called()

    def test_wrong_account_and_trailing_letters_are_not_accepted(self):
        for observed in ('测试角色009', '测试角色001本', '测试角色009★', ''):
            with self.subTest(observed=observed):
                task = self.task('测试角色001')
                with patch(MODULE + '.LoginHandler'), patch(MODULE + '.RuleOcr') as ocr:
                    ocr.return_value.ocr.return_value = observed
                    with self.assertRaises(RequestHumanTakeover):
                        task.switchAccount(skip_harvest=True)
                    self.assertEqual(ocr.return_value.ocr.call_count, 3)

    def test_trailing_background_star_preserves_exact_nickname(self):
        task = self.task('TEST2')
        with patch(MODULE + '.LoginHandler'), patch(MODULE + '.RuleOcr') as ocr:
            ocr.return_value.ocr.return_value = 'TEST2★'
            self.assertTrue(task.switchAccount(skip_harvest=True))
        for observed in ('TEST20★', 'TEST3★', 'TEST2本★', 'TE★ST2'):
            self.assertNotEqual(SwitchAccount.verification_name(observed), 'TEST2')

    def test_trailing_ocr_comma_preserves_exact_account_number(self):
        task = self.task('测试角色10')
        with patch(MODULE + '.LoginHandler'), patch(MODULE + '.RuleOcr') as ocr:
            ocr.return_value.ocr.return_value = '测试角色10、'
            self.assertTrue(task.switchAccount(skip_harvest=True))
        for observed in ('测试角色100、', '测试角色1、', '测试角色10本、', '测试角色、10'):
            self.assertNotEqual(SwitchAccount.verification_name(observed), '测试角色10')

    def test_eye_identity_recheck_uses_badge_free_roi_and_two_exact_reads(self):
        from tasks.EyeAwakening.script_task import NICK, ScriptTask

        self.assertEqual(tuple(NICK.roi), (125, 25, 120, 32))
        task = object.__new__(ScriptTask)
        task.device = Mock()
        task.ui_get_current_page = Mock()
        task.ui_goto = Mock(return_value=True)
        task.screenshot = Mock()
        for values in (['测试角色001', '测试角色001'], ['测试角色001', '测试角色009'],
                       ['测试角色001★', '测试角色001★']):
            with patch.object(NICK, 'ocr', side_effect=values), \
                    patch('tasks.EyeAwakening.script_task.time.sleep'):
                if values[0] == values[1]:
                    task.verified_identity('测试角色001')
                else:
                    with self.assertRaises(GameStuckError):
                        task.verified_identity('测试角色001')

    def test_eye_entry_refreshes_map_and_scrolls_to_layer_one(self):
        from tasks.EyeAwakening.script_task import ScriptTask

        task = object.__new__(ScriptTask)
        task.device = Mock()
        task.enter_map = Mock()
        task.ui_goto = Mock(return_value=True)
        task.screenshot = Mock()
        task.appear = Mock(side_effect=[False, True, True])
        task.appear_then_click = Mock(return_value=True)
        task.map_visible = Mock(return_value=False)
        import numpy as np
        row = SimpleNamespace(ocr_text='壹层', box=np.array(
            [[30, 32], [42, 32], [42, 52], [30, 52]]))
        with patch('tasks.EyeAwakening.script_task.one_selected', return_value=True), \
                patch('tasks.EyeAwakening.script_task.time.sleep'), \
                patch('tasks.EyeAwakening.script_task.RuleOcr') as reader:
            reader.return_value.detect_and_ocr.side_effect = [[], [row]]
            task.enter_fire_one()
        task.enter_map.assert_called_once()
        task.device.swipe.assert_called_once_with(p1=(164, 180), p2=(164, 580))
        task.device.click.assert_called_once_with(x=160, y=126)

    def test_challenge_retry_is_bounded_and_requires_selected_layer(self):
        from tasks.EyeAwakening.script_task import ScriptTask
        from tasks.EvoZone.script_task import ScriptTask as EvoTask

        task = object.__new__(ScriptTask)
        task.device = Mock()
        task.screenshot = Mock()
        task.appear = Mock(return_value=True)
        task.click = Mock(return_value=True)
        with patch.object(EvoTask, 'battle_before', side_effect=[False, True]), \
                patch('tasks.EyeAwakening.script_task.one_selected', return_value=True):
            self.assertTrue(task.battle_before(None, SimpleNamespace()))
        task.click.assert_called_once_with(task.I_EVOZONE_FIRE, interval=1)
        task.click.reset_mock()
        with patch.object(EvoTask, 'battle_before', return_value=False) as prepare, \
                patch('tasks.EyeAwakening.script_task.one_selected', return_value=True):
            self.assertFalse(task.battle_before(None, SimpleNamespace()))
        self.assertEqual(prepare.call_count, 3)
        self.assertEqual(task.click.call_count, 2)
        task.click.reset_mock()
        with patch.object(EvoTask, 'battle_before', return_value=False), \
                patch('tasks.EyeAwakening.script_task.one_selected', return_value=False):
            self.assertFalse(task.battle_before(None, SimpleNamespace()))
        task.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
