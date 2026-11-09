import json
import os
import tempfile
import unittest
import numpy as np
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from module.exception import GameStuckError, ScriptEnd, TaskEnd
from tasks.EyeAwakening.script_task import ScriptTask
from tasks.EyeAwakening.inventory import InventoryUncertain, combine_boundaries, read_inventory_frame
from tasks.EyeAwakening.notification import notify_completion
from tasks.EyeAwakening.profile import PROFILES


class EyeFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp.name)
        self.a = NS(character='小号一', account='abcd123@example.test')
        self.b = NS(character='小号二', account='wxyz123@example.test')
        selection = NS(characters='小号一\n小号二', server='测试服')
        eye = NS(scheduler=NS(enable=True), options=NS(max_battles_per_account=10))
        model = NS(guild_quick_participation=NS(guild_accounts=selection), eye_awakening=eye)
        self.config = NS(config_name='oas_leveling', model=model,
                         find_jade=NS(sup_account_list=[]), save=lambda: None)
        self.task = object.__new__(ScriptTask)
        self.task.config = self.config
        self.task.device = NS(image=object())
        self.task.verified_identity = lambda name: None
        self.task.enter_map = lambda: None
        self.task.enter_fire_one = lambda: None
        self.task.screenshot = lambda: None
        self.task.appear = lambda rule: True
        self.task.click = lambda *a, **kw: True
        self.task.return_to_map = lambda: None
        self.task.run_general_battle = lambda config: True
        self.task.inventory_counts = lambda: {5: 2, 6: 1}
        self.task.leave_inventory = lambda: None
        self.patches = [patch('tasks.EyeAwakening.script_task.select_accounts', return_value=[self.a, self.b]),
                        patch('tasks.EyeAwakening.script_task.FindJadeTask.switch_support_account', return_value=True),
                        patch('tasks.EyeAwakening.script_task.one_selected', return_value=True),
                        patch('tasks.EyeAwakening.script_task.notify_completion', return_value='accepted')]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        os.chdir(self.old_cwd)
        self.temp.cleanup()

    def ledger(self):
        path = next(Path('log/EyeAwakening/oas_leveling').glob('*.json'))
        return json.loads(path.read_text(encoding='utf8'))

    def test_completion_uses_per_account_progress(self):
        values = iter([49, 50, 50])
        self.task.map_progress = lambda: next(values)
        with self.assertRaises(TaskEnd):
            self.task.run()
        state = self.ledger()
        self.assertEqual(state['status'], '完成')
        self.assertEqual(state['accounts']['小号一']['battles'], 1)
        self.assertEqual(state['accounts']['小号二']['battles'], 0)
        self.assertTrue(all(x['completed'] and x['progress'] == 50 for x in state['accounts'].values()))
        self.assertFalse(self.config.model.eye_awakening.scheduler.enable)
        self.assertEqual(state['accounts']['小号一']['inventory']['five_star'], 2)
        self.assertEqual(state['accounts']['小号一']['inventory']['six_star'], 1)
        self.assertEqual(state['accounts']['小号一']['notification']['status'], 'accepted')

    def test_unconfirmed_battle_retains_pending_checkpoint(self):
        self.task.map_progress = lambda: 1
        def fail(config):
            raise GameStuckError('未确认结算')
        self.task.run_general_battle = fail
        with self.assertRaises(ScriptEnd):
            self.task.run()
        state = self.ledger()
        self.assertTrue(state['accounts']['小号一']['battle_pending'])
        self.assertEqual(state['accounts']['小号一']['progress'], 1)
        self.assertFalse(state['accounts']['小号一'].get('completed', False))
        self.assertNotIn('小号二', state['accounts'])

    def test_victory_without_drop_does_not_finish_account(self):
        values = iter([49, 49, 50, 50])
        self.task.map_progress = lambda: next(values)
        with self.assertRaises(TaskEnd):
            self.task.run()
        state = self.ledger()
        self.assertEqual(state['accounts']['小号一']['battles'], 2)
        self.assertEqual(state['accounts']['小号一']['progress'], 50)

    def test_failed_inventory_notifies_unknown_instead_of_zero(self):
        self.task.map_progress = lambda: 50
        def fail():
            raise InventoryUncertain('列表未确认')
        self.task.inventory_counts = fail
        with self.assertRaises(TaskEnd):
            self.task.run()
        self.assertIsNone(self.ledger()['accounts']['小号一']['inventory']['five_star'])

    def test_interrupted_send_is_not_automatically_repeated(self):
        self.task.map_progress = lambda: 50
        with self.assertRaises(TaskEnd):
            self.task.run()
        path = next(Path('log/EyeAwakening/oas_leveling').glob('*.json'))
        state = self.ledger()
        state['accounts']['小号一']['notification']['status'] = 'sending'
        path.write_text(json.dumps(state, ensure_ascii=False), encoding='utf8')
        with patch('tasks.EyeAwakening.script_task.notify_completion') as push:
            with self.assertRaises(TaskEnd):
                self.task.run()
        self.assertEqual(push.call_count, 0)
        self.assertEqual(self.ledger()['accounts']['小号一']['notification']['status'], 'uncertain')


class InventoryAndNotificationTest(unittest.TestCase):
    def test_three_profiles_have_disjoint_accounts_and_devices(self):
        groups = list(PROFILES.values())
        self.assertEqual([len(g['characters']) for g in groups], [4, 4, 4])
        self.assertEqual(len({name for g in groups for name in g['characters']}), 12)
        self.assertEqual(len({g['window'] for g in groups}), 3)
        self.assertEqual(len({g['serial'] for g in groups}), 3)

    def test_complete_boundary_counts_and_conflicts(self):
        self.assertEqual(combine_boundaries({2: 2, 3: 2}, {2: 2, 3: 2}), {5: 0, 6: 0})
        self.assertEqual(combine_boundaries({1: 1, 5: 2}, {5: 2, 6: 3}), {5: 2, 6: 3})
        with self.assertRaises(InventoryUncertain):
            combine_boundaries({1: 1}, {5: 1, 6: 1})
        with self.assertRaises(InventoryUncertain):
            combine_boundaries({5: 2}, {5: 3})

    def test_push_includes_character_and_unknown_is_not_zero(self):
        settings = NS(notify_enable=True, notify_config='provider: fake')
        config = NS(model=NS(script=NS(error=settings)), config_name='oas_leveling')
        notifier = NS(config_name='', push=lambda **kwargs: True)
        with patch('tasks.EyeAwakening.notification.Notifier', return_value=notifier), \
             patch.object(notifier, 'push', return_value=True) as push:
            self.assertEqual(notify_completion(config, '小号一', {5: 2, 6: None}, 'abcd123@example.test'), 'accepted')
        body = push.call_args.kwargs['content']
        self.assertIn('账号：小号一（abcd）', body)
        self.assertNotIn('abcd123@example.test', body)
        self.assertIn('五星裂变之眼：2个', body)
        self.assertIn('六星裂变之眼：未识别', body)

    def test_missing_ocr_row_is_not_treated_as_zero(self):
        def row(text, y):
            return NS(ocr_text=text, box=np.array([[110,y-10],[250,y-10],[250,y+10],[110,y+10]]))
        rows = [row('二星裂变之眼', 27), row('持有：2', 70),
                row('三星裂变之眼', 127), row('持有：2', 170)]
        reader = NS(detect_and_ocr=lambda image: rows)
        with patch('tasks.EyeAwakening.inventory.RuleOcr', return_value=reader), \
             patch('tasks.EyeAwakening.inventory._card_borders', return_value=[155, 255, 355]):
            with self.assertRaises(InventoryUncertain):
                read_inventory_frame(np.zeros((720,1280,3), dtype=np.uint8))


if __name__ == '__main__':
    unittest.main()
