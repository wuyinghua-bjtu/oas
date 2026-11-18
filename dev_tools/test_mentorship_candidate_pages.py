import unittest
from unittest.mock import patch

import numpy as np

from tasks.Mentorship.normal_device import NormalDevices


class FakeDevice:
    def __init__(self):
        self.image = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.clicks = []

    def screenshot(self):
        return self.image

    def click(self, *point, **kwargs):
        self.clicks.append(point)


class CandidatePageTests(unittest.TestCase):
    def make_pair(self, results):
        return NormalDevices(FakeDevice(), FakeDevice(), '测试徒弟', lambda _: results)

    def test_current_page_match_does_not_switch(self):
        pair = self.make_pair([])
        with patch.object(pair, '_wait', return_value=(400, 220)):
            self.assertEqual(pair.find_invitation_candidate(), (400, 220))
        self.assertEqual(pair.mentor.clicks, [])

    @patch('tasks.Mentorship.normal_device.time.sleep')
    @patch('tasks.Mentorship.normal_device.Invite.I_INVITE_ENSURE.match', return_value=True)
    def test_searches_recent_then_guild(self, room, sleep):
        pair = self.make_pair([('最近', (470, 125, 40, 20)), ('寮友', (590, 125, 40, 20))])
        with patch.object(pair, '_wait', side_effect=[None, None, (405, 230)]):
            self.assertEqual(pair.find_invitation_candidate(), (405, 230))
        self.assertEqual(pair.mentor.clicks, [(490, 135), (610, 135)])

    @patch('tasks.Mentorship.normal_device.Invite.I_INVITE_ENSURE.match', return_value=True)
    def test_ambiguous_and_outside_tabs_are_not_clicked(self, room):
        pair = self.make_pair([('最近', (470, 125, 40, 20)), ('最近', (520, 125, 40, 20)),
                               ('寮友', (590, 200, 40, 20))])
        with patch.object(pair, '_wait', return_value=None):
            self.assertIsNone(pair.find_invitation_candidate())
        self.assertEqual(pair.mentor.clicks, [])

    @patch('tasks.Mentorship.normal_device.time.sleep')
    @patch('tasks.Mentorship.normal_device.Invite.I_INVITE_ENSURE.match', return_value=True)
    def test_upper_tab_row_matches_general_invite_layout(self, room, sleep):
        pair = self.make_pair([('最近', (470, 94, 40, 20)), ('跨区', (703, 91, 40, 20))])
        with patch.object(pair, '_wait', side_effect=[None, None, (405, 230)]):
            self.assertEqual(pair.find_invitation_candidate(), (405, 230))
        self.assertEqual(pair.mentor.clicks, [(490, 104), (723, 101)])

    @patch('tasks.Mentorship.normal_device.Invite.I_INVITE_ENSURE.match', return_value=True)
    def test_room_header_is_not_an_invitation_tab(self, room):
        pair = self.make_pair([('最近', (470, 60, 40, 20)), ('跨区', (703, 170, 40, 20))])
        with patch.object(pair, '_wait', return_value=None):
            self.assertIsNone(pair.find_invitation_candidate())
        self.assertEqual(pair.mentor.clicks, [])

    @patch('tasks.Mentorship.normal_device.Invite.I_INVITE_ENSURE.match', return_value=False)
    def test_closed_dialog_stops_search(self, room):
        pair = self.make_pair([('最近', (470, 125, 40, 20))])
        with patch.object(pair, '_wait', return_value=None):
            self.assertIsNone(pair.find_invitation_candidate())
        self.assertEqual(pair.mentor.clicks, [])


if __name__ == '__main__':
    unittest.main()
