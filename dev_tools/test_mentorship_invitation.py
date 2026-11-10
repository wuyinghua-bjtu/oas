import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from tasks.Mentorship.vision import guard_accept_position
from tasks.Mentorship.invitation import accept_guard_invitation, invite_guard_with_listener


class InvitationTests(unittest.TestCase):
    def test_banner_moves_and_other_pages_are_ignored(self):
        p = Path(r'C:\Users\wyh\AppData\Local\Temp\codex-clipboard-23ffb638-c6cc-4b62-841c-cd3b56868f48.png')
        image = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
        self.assertEqual(guard_accept_position(image), (140, 250))
        shifted = np.zeros_like(image)
        shifted[:, :-40] = image[:, 40:]
        self.assertEqual(guard_accept_position(shifted), (100, 250))
        self.assertIsNone(guard_accept_position(np.zeros_like(image)))

    def test_click_without_room_is_not_success(self):
        class Device:
            image = None
            def screenshot(self): pass
            def click(self, *point): pass
        with patch('tasks.Mentorship.invitation.guard_accept_position', return_value=(140, 250)), \
             patch('tasks.Mentorship.invitation.detect', return_value=None):
            self.assertFalse(accept_guard_invitation(Device(), timeout=0.01, interval=0.001))

    def test_listener_is_ready_before_invitation(self):
        order = []
        def listen(device, timeout, interval, ready):
            order.append('listen')
            ready.set()
            return True
        def send():
            order.append('send')
            return True
        with patch('tasks.Mentorship.invitation.accept_guard_invitation', side_effect=listen):
            self.assertTrue(invite_guard_with_listener(object(), send))
        self.assertEqual(order, ['listen', 'send'])


if __name__ == '__main__':
    unittest.main()
