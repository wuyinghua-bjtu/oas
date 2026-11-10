import unittest
from module.config.local_values import local_text
from pathlib import Path
import cv2
from tasks.Mentorship.guard import GuardAction, decide_guard_invite, decide_guard_ready

ROOT=Path(r'C:\Users\wyh\AppData\Local\Temp')
def image(name):
    return cv2.cvtColor(cv2.imread(str(ROOT / name)), cv2.COLOR_BGR2RGB)

class GuardTests(unittest.TestCase):
    def test_exact_apprentice_required(self):
        invite=image('codex-clipboard-6b1a05b6-9162-4ea9-a841-2969e0e0e580.png')
        blank=image('codex-clipboard-524d1707-7b50-47f6-b7ad-f7ea4c943ce2.png')
        self.assertEqual(decide_guard_invite(invite,blank,local_text('LOCAL_OCR_NAME03'),local_text('LOCAL_OCR_NAME03')),GuardAction.SELECT_APPRENTICE)
        self.assertEqual(decide_guard_invite(invite,blank,'别的账号',local_text('LOCAL_OCR_NAME03')),GuardAction.WAIT)
    def test_both_players_and_locks_required(self):
        mentor=image('codex-clipboard-5c0e0b8b-5b84-447c-a52f-47c6787e9d65.png')
        apprentice=image('codex-clipboard-d7c55dfa-ce48-4e14-8ae5-7a763b42ab74.png')
        self.assertEqual(decide_guard_ready(mentor,apprentice,True),GuardAction.LOCK_APPRENTICE)
        self.assertEqual(decide_guard_ready(mentor,apprentice,False),GuardAction.WAIT)
if __name__ == '__main__': unittest.main()

