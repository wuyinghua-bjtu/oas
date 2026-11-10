import os
from module.config.local_values import local_text
import unittest
import cv2
import numpy as np
from tasks.Mentorship.normal_invitation import experience_invitation_position
from tasks.Mentorship.identity import normal_rooms_have_pair


def image(name):
    path = os.path.join(os.environ['TEMP'], name)
    data = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    return cv2.cvtColor(data, cv2.COLOR_BGR2RGB)


class NormalInvitationTests(unittest.TestCase):
    def test_live_recording_identifies_correct_invite_and_pair(self):
        invitation = image('mentorship-invitation.png')
        self.assertIsNotNone(experience_invitation_position(invitation))
        mentor = image('mentorship-room-mentor.png')
        apprentice = image('mentorship-room-apprentice.png')
        self.assertTrue(normal_rooms_have_pair(mentor, apprentice, local_text('LOCAL_OCR_NAME03')))
        self.assertFalse(normal_rooms_have_pair(mentor, apprentice, '其他名字'))
        self.assertFalse(normal_rooms_have_pair(mentor, np.zeros_like(apprentice), local_text('LOCAL_OCR_NAME03')))


if __name__ == '__main__':
    unittest.main()
