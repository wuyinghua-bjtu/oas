import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from tasks.EyeAwakening.config import EyeAwakening, resolve_eye_accounts
from tasks.EyeAwakening.profile import PROFILES, validate_profile
from module.exception import RequestHumanTakeover
from module.config.config_model import ConfigModel


class EyeAccountConfigTest(unittest.TestCase):
    def test_editable_slots_resolve_in_order(self):
        eye = EyeAwakening(eye_account_1={'character': '新小号一', 'svr': '测试服', 'account': 'one@example.test'},
                           eye_account_3={'character': '新小号三', 'svr': '测试服', 'account': 'three@example.test'})
        accounts = resolve_eye_accounts(eye)
        self.assertEqual([a.character for a in accounts], ['新小号一', '新小号三'])
        self.assertEqual(resolve_eye_accounts(EyeAwakening(**eye.model_dump()))[1].account, 'three@example.test')

    def test_incomplete_empty_and_duplicate_are_rejected(self):
        for eye in (EyeAwakening(), EyeAwakening(eye_account_1={'character': '小号'}),
                    EyeAwakening(eye_account_1={'character': '重复', 'svr': '服', 'account': 'one'},
                                 eye_account_2={'character': '重复', 'svr': '服', 'account': 'two'})):
            with self.assertRaises(ValueError):
                resolve_eye_accounts(eye)

    def test_gui_and_edit_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            raw = json.loads(Path('config/oas_eye_1.json').read_text(encoding='utf8'))
            with patch.object(ConfigModel, 'read_json', return_value=copy.deepcopy(raw)), \
                 patch.object(ConfigModel, 'write_json', side_effect=lambda name,data: (directory/(name+'.json')).write_text(json.dumps(data,default=str),encoding='utf8')):
                model = ConfigModel('oas_eye_1')
                args = model.script_task('EyeAwakening')
                self.assertTrue(all(f'eye_account_{i}' in args for i in range(1,5)))
                self.assertTrue(model.script_set_arg('EyeAwakening','eye_account_1','character','修改后角色'))
                saved = json.loads((directory/'oas_eye_1.json').read_text(encoding='utf8'))
                self.assertEqual(saved['eye_awakening']['eye_account_1']['character'],'修改后角色')
                self.assertEqual(raw['find_jade'], saved['find_jade'])

    def test_existing_profiles_migrated_and_disjoint(self):
        all_names = []
        for name in PROFILES:
            raw = json.loads(Path('config',name+'.json').read_text(encoding='utf8'))
            accounts = resolve_eye_accounts(EyeAwakening(**raw['eye_awakening']))
            self.assertEqual(len(accounts), 4)
            all_names.extend((a.svr,a.character) for a in accounts)
        self.assertEqual(len(set(all_names)),12)


if __name__ == '__main__':
    unittest.main()
