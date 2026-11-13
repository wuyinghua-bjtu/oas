import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.GuildQuickParticipation.netherworld import title
from tasks.Hunt.assets import HuntAssets


class NetherworldTitleTests(unittest.TestCase):
    def test_ranking_and_challenge_identify_vertical_title_page(self):
        task = SimpleNamespace(appear=Mock(return_value=True))
        with patch('tasks.GuildQuickParticipation.netherworld.words', return_value='排行成员消灭轮数70'):
            self.assertTrue(title(task))
        task.appear.assert_called_once_with(HuntAssets.I_NW_CHALLAGE)

    def test_banner_does_not_require_old_top_title(self):
        task = SimpleNamespace(appear=Mock(return_value=True))
        with patch('tasks.GuildQuickParticipation.netherworld.words', return_value='成员消灭轮数') as reader:
            self.assertTrue(title(task))
        self.assertEqual(reader.call_args.args[1], (600,100,630,400))

    def test_map_room_and_unrelated_ranking_rejected(self):
        task = SimpleNamespace(appear=Mock(return_value=False))
        with patch('tasks.GuildQuickParticipation.netherworld.words') as reader:
            self.assertFalse(title(task))
            reader.assert_not_called()
        task.appear.return_value = True
        for text in ('阴界之门', '排行', '挑战开始轮数队伍预设', ''):
            with self.subTest(text=text), patch('tasks.GuildQuickParticipation.netherworld.words', return_value=text):
                self.assertFalse(title(task))


if __name__ == '__main__':
    unittest.main()
