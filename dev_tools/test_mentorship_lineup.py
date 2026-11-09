import unittest
from unittest.mock import patch
from tasks.Mentorship.lineup import lock_guard_lineups


class Device:
    def __init__(self, image):
        self.image, self.clicks = image, []
    def screenshot(self): pass
    def click(self, x, y): self.clicks.append((x, y))


class LineupTests(unittest.TestCase):
    def test_unknown_identity_never_clicks(self):
        m, a = Device('mentor'), Device('apprentice')
        with patch('tasks.Mentorship.lineup.detect', return_value=True), \
             patch('tasks.Mentorship.lineup.lineup_state', return_value='unlock'):
            self.assertFalse(lock_guard_lineups(m, a, lambda *_: False, timeout=.01))
        self.assertEqual(m.clicks + a.clicks, [])

    def test_both_must_be_locked(self):
        m, a = Device('mentor'), Device('apprentice')
        with patch('tasks.Mentorship.lineup.detect', return_value=True), \
             patch('tasks.Mentorship.lineup.lineup_state', return_value='lock'):
            self.assertTrue(lock_guard_lineups(m, a, lambda *_: True, timeout=1))
        self.assertEqual(m.clicks + a.clicks, [])


if __name__ == '__main__': unittest.main()
