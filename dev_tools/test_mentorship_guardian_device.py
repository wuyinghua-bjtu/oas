import unittest
from pathlib import Path
import cv2
import numpy as np
from tasks.Mentorship.guardian_device import GuardianDevices, _selected
from tasks.Mentorship.vision import detect


class Device:
    def __init__(self, image): self.image, self.clicks = image, []
    def screenshot(self): pass
    def click(self, *args, **kwargs): self.clicks.append(args)


class GuardianDeviceTests(unittest.TestCase):
    def image(self, name):
        p = Path(r'C:\Users\OASUser\AppData\Local\Temp') / name
        return cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)

    def test_entry_and_player_page_are_distinct(self):
        master = self.image('codex-clipboard-5c0e0b8b-5b84-447c-a52f-47c6787e9d65.png')
        apprentice = self.image('codex-clipboard-d7c55dfa-ce48-4e14-8ae5-7a763b42ab74.png')
        empty = self.image('codex-clipboard-cf300e95-0f14-4b6e-8b76-bea3fd21fec2.png')
        self.assertIsNotNone(detect(master, 'guard_challenge'))
        self.assertIsNone(detect(apprentice, 'guard_challenge'))
        pair = GuardianDevices(Device(master), Device(apprentice), '冥界画师03')
        self.assertTrue(pair._both_confirmed(master, apprentice))
        self.assertFalse(pair._both_confirmed(master, empty))

    def test_cyan_selection_required(self):
        image = self.image('codex-clipboard-6b1a05b6-9162-4ea9-a841-2969e0e0e580.png')
        self.assertFalse(_selected(image, (500, 201)))
        image[181:241, 410:605] = (150, 215, 230)
        self.assertTrue(_selected(image, (500, 201)))

    def test_unknown_initial_screen_does_not_click(self):
        unknown = np.zeros((720, 1280, 3), np.uint8)
        mentor, pupil = Device(unknown), Device(unknown)
        self.assertFalse(GuardianDevices(mentor, pupil, '冥界画师03').invite_and_lock())
        self.assertEqual(mentor.clicks + pupil.clicks, [])


if __name__ == '__main__': unittest.main()
