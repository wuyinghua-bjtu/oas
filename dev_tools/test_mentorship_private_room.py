import unittest
from unittest.mock import patch

from tasks.Mentorship.private_room import create_private_room, Room


class Device:
    image = object()

    def __init__(self):
        self.clicks = []

    def screenshot(self):
        pass

    def click(self, *args, **kwargs):
        self.clicks.append(args)


class PrivateRoomTests(unittest.TestCase):
    def test_wrong_activity_never_creates(self):
        device = Device()
        with patch.object(Room.O_GR_ZONES_NAME, 'ocr', return_value='金币妖怪'):
            self.assertFalse(create_private_room(device, 'experience', timeout=.1))
        self.assertEqual(device.clicks, [])

    def test_unknown_activity_rejected(self):
        with self.assertRaises(ValueError):
            create_private_room(Device(), 'unknown')


if __name__ == '__main__':
    unittest.main()
