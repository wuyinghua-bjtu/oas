import unittest
from types import SimpleNamespace

from tasks.Component.SwitchAccount.switch_account_config import AccountInfo
from tasks.GuildQuickParticipation.config import GuildQuickParticipation
from tasks.GuildQuickParticipation.policy import SUPPORT_CHARACTERS, select_accounts
from module.config.config_model import ConfigModel


class GuildAccountSelectionTests(unittest.TestCase):
    def test_defaults_include_new_account_and_resolve(self):
        self.assertIn('OASPlayer001', SUPPORT_CHARACTERS)
        accounts = [AccountInfo(character=n, svr='砂狐乐园') for n in SUPPORT_CHARACTERS]
        group = GuildQuickParticipation().guild_accounts
        self.assertEqual([a.character for a in select_accounts(accounts, group.characters, group.server)],
                         list(SUPPORT_CHARACTERS))

    def test_missing_or_duplicate_name_fails(self):
        account = AccountInfo(character='角色', svr='砂狐乐园')
        for text, accounts in [('角色\n角色', [account]), ('未知', [account]), ('角色', [account, account])]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                select_accounts(accounts, text, '砂狐乐园')

    def test_gui_exposes_selection(self):
        groups = ConfigModel().script_task('GuildQuickParticipation')
        fields = {item['name']: item for item in groups['guild_accounts']}
        self.assertEqual(fields['characters']['type'], 'multi_line')
        self.assertIn('OASPlayer001', fields['characters']['value'])


if __name__ == '__main__': unittest.main()
