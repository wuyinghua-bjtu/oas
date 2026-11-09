import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tasks.Mentorship.guard_remaining import read_remaining


class Counter:
    def __init__(self, values):
        self.values = iter(values)

    def ocr(self, image):
        return next(self.values)


class Device:
    image = object()

    def screenshot(self):
        pass


class GuardRemainingTests(unittest.TestCase):
    @patch('tasks.Mentorship.guard_remaining.time.sleep')
    @patch('tasks.Mentorship.guard_remaining.detect', return_value=True)
    def test_requires_valid_repeated_reading(self, _detect, _sleep):
        counter = Counter([(0, 0, 0), (4, 1, 5), (4, 1, 5)])
        self.assertEqual(read_remaining(Device(), counter=counter), 4)

    @patch('tasks.Mentorship.guard_remaining.time.sleep')
    @patch('tasks.Mentorship.guard_remaining.detect', return_value=True)
    def test_zero_is_valid_only_with_total_five(self, _detect, _sleep):
        counter = Counter([(0, 0, 0), (0, 5, 5), (0, 5, 5)])
        self.assertEqual(read_remaining(Device(), counter=counter), 0)


if __name__ == '__main__':
    unittest.main()
