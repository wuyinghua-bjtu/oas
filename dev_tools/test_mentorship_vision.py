import unittest
import cv2
from pathlib import Path
from tasks.Mentorship.vision import detect

class VisionTests(unittest.TestCase):
    def test_known_page_markers(self):
        root=Path(r'C:\Users\OASUser\AppData\Local\Temp')
        pairs=[('codex-clipboard-524d1707-7b50-47f6-b7ad-f7ea4c943ce2.png','guard_entry'),
               ('codex-clipboard-cf300e95-0f14-4b6e-8b76-bea3fd21fec2.png','guard_invite_entry'),
               ('codex-clipboard-6b1a05b6-9162-4ea9-a841-2969e0e0e580.png','guard_invite_title'),
               ('codex-clipboard-23ffb638-c6cc-4b62-841c-cd3b56868f48.png','guard_invitation'),
               ('codex-clipboard-5c0e0b8b-5b84-447c-a52f-47c6787e9d65.png','guard_room')]
        for name,kind in pairs:
            image=cv2.cvtColor(cv2.imread(str(root/name)),cv2.COLOR_BGR2RGB)
            self.assertIsNotNone(detect(image,kind),kind)
            for _,other in pairs:
                if other != kind and not (other == 'guard_room' and kind in ('guard_invite_entry', 'guard_invite_title')):
                    self.assertIsNone(detect(image,other),f'{kind} falsely matched {other}')
if __name__ == '__main__': unittest.main()


class LockVisionTests(unittest.TestCase):
    def test_guard_room_is_locked(self):
        from tasks.Mentorship.vision import lineup_state
        p=Path(r'C:\Users\OASUser\AppData\Local\Temp\codex-clipboard-5c0e0b8b-5b84-447c-a52f-47c6787e9d65.png')
        image=cv2.cvtColor(cv2.imread(str(p)),cv2.COLOR_BGR2RGB)
        self.assertEqual(lineup_state(image),'lock')

    def test_apprentice_room_is_unlocked(self):
        from tasks.Mentorship.vision import lineup_state
        p=Path(r'C:\Users\OASUser\AppData\Local\Temp\codex-clipboard-d7c55dfa-ce48-4e14-8ae5-7a763b42ab74.png')
        image=cv2.cvtColor(cv2.imread(str(p)),cv2.COLOR_BGR2RGB)
        self.assertEqual(lineup_state(image),'unlock')
