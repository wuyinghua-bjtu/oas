import unittest
from datetime import date
from tasks.Mentorship.plan import MentorSettings, daily_plan

class PlanTests(unittest.TestCase):
    def test_weekday_and_weekend(self):
        weekday = daily_plan(date(2026, 10, 30))
        weekend = daily_plan(date(2026, 10, 31))
        self.assertEqual([a.name for a in weekday], ['guard','experience','gold','tako','apprentice_souls'])
        self.assertEqual([a.name for a in weekend], ['guard','experience','gold','apprentice_souls'])
        self.assertEqual([a.rounds for a in weekday], [None,2,2,2,15])
        self.assertTrue(weekday[-2].mentor_exit_after_prepare)
        self.assertEqual(weekday[1].mentor_buffs, ('exp_50','exp_100'))
        self.assertEqual(weekday[2].mentor_buffs, ('gold_50','gold_100'))
    def test_device_profiles_must_differ(self):
        with self.assertRaises(ValueError):
            MentorSettings(mentor_profile='same', apprentice_profile='same').validate()

if __name__ == '__main__': unittest.main()
