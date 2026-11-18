import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.Mentorship.daily_device import run_verified_daily


class SelectedActivityTests(unittest.TestCase):
    def test_normal_resume_never_enters_guardian_or_other_activities(self):
        apprentice_config = SimpleNamespace(config_name='oas_leveling')
        with ExitStack() as stack:
            patched = {name: stack.enter_context(patch('tasks.Mentorship.daily_device.' + name))
                       for name in ('apply_mentor_soul_preset', 'GameUi', 'GeneralRoom', 'RuleOcr',
                                    'NormalDevices', 'GuardianDevices', 'MasterBuffs', 'go_activity_menu',
                                    'read_remaining', 'read_normal_remaining', 'run_apprentice_souls',
                                    'PairBattle', 'leave_activity_menu')}
            patched['go_activity_menu'].return_value = True
            patched['read_normal_remaining'].return_value = 0
            self.assertTrue(run_verified_daily(Mock(), Mock(), Mock(), 'apprentice',
                                               apprentice_config=apprentice_config,
                                               activities=('experience', 'gold')))
            patched['read_remaining'].assert_not_called()
            patched['GuardianDevices'].return_value.invite_and_lock.assert_not_called()
            patched['run_apprentice_souls'].assert_not_called()
            patched['PairBattle'].assert_not_called()
            patched['read_normal_remaining'].assert_has_calls([
                unittest.mock.call(unittest.mock.ANY, 'experience'),
                unittest.mock.call(unittest.mock.ANY, 'gold')])
            self.assertEqual(patched['go_activity_menu'].call_count, 1)

    def test_invalid_scope_rejected_before_device_actions(self):
        with patch('tasks.Mentorship.daily_device.apply_mentor_soul_preset') as preset:
            with self.assertRaises(ValueError):
                run_verified_daily(Mock(), Mock(), Mock(), 'apprentice',
                                   apprentice_config=SimpleNamespace(config_name='oas_leveling'),
                                   activities=('unknown',))
            preset.assert_not_called()


if __name__ == '__main__':
    unittest.main()
