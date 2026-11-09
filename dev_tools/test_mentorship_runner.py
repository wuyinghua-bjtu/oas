import unittest
from datetime import date
from unittest.mock import Mock
from tasks.Mentorship.plan import MentorSettings
from tasks.Mentorship.runner import execute_daily, VerificationError

class RunnerTests(unittest.TestCase):
    def adapter(self):
        a=Mock()
        a.validate_bindings.return_value=True
        a.guard_remaining.side_effect=[2,1,0]
        for name in ('guard_invite','guard_zero_confirmed','lock_both_lineups','guard_battle','set_mentor_buff','create_private_room','invite_and_verify','start_battle','mentor_exit_after_prepare','wait_battle_result','apprentice_souls'):
            getattr(a,name).return_value=True
        return a
    def test_weekday_full_sequence(self):
        a=self.adapter(); execute_daily(a,MentorSettings(),date(2026,10,30))
        self.assertEqual(a.guard_battle.call_count,2)
        self.assertEqual(a.create_private_room.call_count,6)
        self.assertEqual(a.mentor_exit_after_prepare.call_count,2)
        self.assertEqual(a.set_mentor_buff.call_count,8)
        a.apprentice_souls.assert_called_once_with(15)
    def test_cleanup_on_failure(self):
        a=self.adapter(); a.create_private_room.return_value=False
        with self.assertRaises(VerificationError): execute_daily(a,MentorSettings(),date(2026,10,30))
        self.assertTrue(any(c.args == ('exp_50', False) for c in a.set_mentor_buff.call_args_list))
        self.assertTrue(any(c.args == ('exp_100', False) for c in a.set_mentor_buff.call_args_list))
    def test_guard_must_make_progress(self):
        a=self.adapter(); a.guard_battle.side_effect=[True,False]
        with self.assertRaises(VerificationError): execute_daily(a,MentorSettings(),date(2026,10,30))
        self.assertEqual(a.guard_battle.call_count,2)

    def test_no_repeat_if_guard_count_does_not_decrease(self):
        a=self.adapter(); a.guard_remaining.side_effect=[2,2]
        with self.assertRaises(VerificationError): execute_daily(a,MentorSettings(),date(2026,10,30))
        self.assertEqual(a.guard_battle.call_count,1)

if __name__ == '__main__': unittest.main()

