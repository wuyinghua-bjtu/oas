import unittest
from unittest.mock import patch
from tasks.Mentorship.battle_pair import PairBattle, Battle, Invite, Game, Experience, Gold


class Device:
    def __init__(self): self.image, self.clicks = set(), []
    def screenshot(self): pass
    def click(self, x, y, **kwargs): self.clicks.append((x, y))


class PairBattleTests(unittest.TestCase):
    def setUp(self):
        self.patches = []
        for owner, names in ((Battle, ('I_FALSE', 'I_EXIT_ENSURE', 'I_EXIT', 'I_PREPARE_HIGHLIGHT',
                                      'I_WIN', 'I_DE_WIN', 'I_REWARD', 'I_REWARD_GOLD', 'I_REWARD_STATISTICS')),
                             (Game, ('I_CHECK_MAIN', 'I_CHECK_TEAM')), (Invite, ('I_GI_SURE',)),
                             (Experience, ('I_EXP_WIN',)), (Gold, ('I_GOLD_WIN',))):
            for name in names:
                asset = getattr(owner, name)
                patcher = patch.object(asset, 'match', side_effect=lambda frame, n=name: n in frame)
                patcher.start()
                self.patches.append(patcher)

    def tearDown(self):
        for patcher in self.patches: patcher.stop()

    def test_stone_requires_ready_exit_confirmation_and_return(self):
        mentor, pupil = Device(), Device()
        pair = PairBattle(mentor, pupil)
        side = pair.mentor
        mentor.image = {'I_PREPARE_HIGHLIGHT'}
        self.assertFalse(pair._advance(side, True))
        self.assertTrue(side.ready_clicked)
        side.last_action = 0
        mentor.image = {'I_EXIT'}
        self.assertFalse(pair._advance(side, True))
        side.last_action = 0
        mentor.image = {'I_CHECK_MAIN'}
        self.assertFalse(pair._advance(side, True))
        mentor.image = {'I_EXIT_ENSURE'}
        self.assertFalse(pair._advance(side, True))
        mentor.image = {'I_CHECK_MAIN'}
        self.assertTrue(pair._advance(side, True))
        self.assertEqual(mentor.clicks, [(1180, 590), (37, 33), (755, 438)])
        self.assertFalse(pair.apprentice.returned)

    def test_apprentice_return_without_victory_is_not_completion(self):
        pair = PairBattle(Device(), Device())
        side = pair.apprentice
        side.device.image = {'I_CHECK_MAIN'}
        self.assertFalse(pair._advance(side))
        side.device.image = {'I_WIN'}
        self.assertFalse(pair._advance(side))
        side.device.image = {'I_CHECK_MAIN'}
        self.assertTrue(pair._advance(side))

    def test_guardian_prompt_is_cancelled_before_master_return(self):
        pair = PairBattle(Device(), Device())
        side = pair.mentor
        side.win_seen = True
        side.device.image = {'prompt', 'I_CHECK_MAIN'}
        with patch('tasks.Mentorship.battle_pair.detect',
                   side_effect=lambda frame, kind: kind == 'guard_continue_prompt' and 'prompt' in frame):
            self.assertFalse(pair._advance(side, guardian=True))
        self.assertFalse(side.returned)
        self.assertEqual(side.device.clicks, [(525, 438)])
        side.device.image = {'guard_entry'}
        with patch('tasks.Mentorship.battle_pair.detect',
                   side_effect=lambda frame, kind: kind == 'guard_entry' and kind in frame):
            self.assertTrue(pair._advance(side, guardian=True))


if __name__ == '__main__': unittest.main()
