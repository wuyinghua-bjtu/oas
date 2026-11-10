import unittest
from module.config.local_values import local_text
from pathlib import Path
import cv2
import numpy as np
from tasks.Mentorship.identity import find_guard_candidate, both_guard_rooms_have_apprentice


class IdentityTests(unittest.TestCase):
    def test_default_candidate_and_other_name(self):
        p = Path(r'C:\Users\wyh\AppData\Local\Temp\codex-clipboard-6b1a05b6-9162-4ea9-a841-2969e0e0e580.png')
        image = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
        self.assertIsNotNone(find_guard_candidate(image, local_text('LOCAL_OCR_NAME03')))
        self.assertIsNone(find_guard_candidate(image, local_text('LOCAL_OCR_NAME04')))
        self.assertIsNone(find_guard_candidate(np.zeros_like(image), local_text('LOCAL_OCR_NAME03')))

    def test_configurable_name_requires_unique_exact_match(self):
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.assertEqual(find_guard_candidate(image, '小明', lambda _: [('小明', (400, 200, 10, 10))]), (405, 205))
        self.assertIsNone(find_guard_candidate(image, '小明', lambda _: [('小明2', (400, 200, 10, 10))]))
        self.assertIsNone(find_guard_candidate(image, '小明', lambda _: [('小明', (1, 2, 10, 10))]))

    def test_guard_room_must_have_name_on_both_devices(self):
        root = Path(r'C:\Users\wyh\AppData\Local\Temp')
        def load(name):
            return cv2.cvtColor(cv2.imread(str(root / name)), cv2.COLOR_BGR2RGB)
        master = load('codex-clipboard-5c0e0b8b-5b84-447c-a52f-47c6787e9d65.png')
        pupil = load('codex-clipboard-d7c55dfa-ce48-4e14-8ae5-7a763b42ab74.png')
        empty = load('codex-clipboard-cf300e95-0f14-4b6e-8b76-bea3fd21fec2.png')
        self.assertTrue(both_guard_rooms_have_apprentice(master, pupil, local_text('LOCAL_OCR_NAME03')))
        self.assertFalse(both_guard_rooms_have_apprentice(master, empty, local_text('LOCAL_OCR_NAME03')))


if __name__ == '__main__': unittest.main()
