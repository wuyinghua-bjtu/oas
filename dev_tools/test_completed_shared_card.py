import unittest

from tasks.FindJade.board_scan import completed_shared_card


class CompletedSharedCardTests(unittest.TestCase):
    def test_both_progress_counters_complete(self):
        self.assertTrue(completed_shared_card('领取 自己击败1次山童 6/6 好友击败天邪鬼绿 8/8'))
        self.assertTrue(completed_shared_card('领取 山 6/6 好友击败天邪鬼绿 8/8'))

    def test_incomplete_or_unrelated_card_rejected(self):
        for text in ('领取自己击败山童5/6好友击败天邪鬼绿8/8',
                     '领取好友击败天邪鬼绿8/8',
                     '自己击败山童6/6好友击败天邪鬼绿8/8',
                     '领取自己击败山童0/0好友击败天邪鬼绿8/8'):
            self.assertFalse(completed_shared_card(text))


if __name__ == '__main__':
    unittest.main()
