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
from tasks.EyeAwakening.progress import ProgressUncertain, read_map_quota


class MapQuotaTest(unittest.TestCase):
    def read(self, top, tracker):
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        rows = [[NS(ocr_text=top)], [NS(ocr_text=tracker)]]
        with patch('tasks.EyeAwakening.progress.MAP_EYE.match', return_value=True), \
                patch('tasks.EyeAwakening.progress.RuleOcr.detect_and_ocr', side_effect=rows):
            return read_map_quota(image)

    def test_font_seven_verified_by_activity_tracker(self):
        self.assertEqual(self.read('1/50', '活动 探索觉醒御魂契灵副本掉落（7/50）'), (7, 50))

    def test_unrelated_counter_cannot_correct_progress(self):
        self.assertEqual(self.read('1/50', '御魂今日掉落（7/50）'), (1, 50))

    def test_other_conflicts_remain_uncertain(self):
        with self.assertRaises(ProgressUncertain):
            self.read('6/50', '活动 探索觉醒御魂契灵副本掉落（7/50）')


class MapProgressRetryTest(unittest.TestCase):
    def setUp(self):
        self.task = object.__new__(ScriptTask)
        self.task.device = NS(image=object())

    def read(self, values, minimum=0):
        self.task._verified_map_floor = minimum
        with patch.object(self.task, 'screenshot'), \
                patch.object(self.task, 'map_visible', return_value=True), \
                patch('tasks.EyeAwakening.script_task.read_map_quota', side_effect=values), \
                patch('tasks.EyeAwakening.script_task.time.sleep'):
            return self.task.map_progress()

    def test_transient_ocr_recovers_after_original_three_attempts(self):
        self.assertEqual(self.read([(1, 50), (7, 50), (1, 50), (7, 50), (7, 50)], 7), 7)

    def test_consecutive_regression_is_not_accepted(self):
        self.assertEqual(self.read([(1, 50), (1, 50), (7, 50), (7, 50)], 7), 7)

    def test_discarded_regression_does_not_reset_valid_confirmation(self):
        self.assertEqual(self.read([(7, 50), (1, 50), (7, 50)], 7), 7)

    def test_retry_remains_bounded(self):
        with self.assertRaises(GameStuckError):
            self.read([(1, 50)] * 12, 7)

    def test_verified_progress_updates_floor(self):
        self.assertEqual(self.read([(8, 50), (8, 50)], 7), 8)
        self.assertEqual(self.task._verified_map_floor, 8)


class EyeFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp.name)
        self.a = NS(character='小号一', account='abcd123@example.test', svr='测试服')
        self.b = NS(character='小号二', account='wxyz123@example.test', svr='测试服')
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
        self.patches = [patch('tasks.EyeAwakening.script_task.resolve_eye_accounts', return_value=[self.a, self.b]),
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
        self.assertTrue(self.config.model.eye_awakening.scheduler.enable)

    def test_invalid_accounts_preserve_enable_selection(self):
        with patch('tasks.EyeAwakening.script_task.resolve_eye_accounts',
                   side_effect=ValueError('invalid accounts')):
            with self.assertRaises(ScriptEnd):
                self.task.run()
        self.assertTrue(self.config.model.eye_awakening.scheduler.enable)

    def test_server_mismatch_preserves_enable_selection(self):
        self.task.map_progress = lambda: 50
        with self.assertRaises(TaskEnd):
            self.task.run()
        self.config.model.eye_awakening.scheduler.enable = True
        self.a.svr = self.b.svr = '另一测试服'
        with self.assertRaises(ScriptEnd):
            self.task.run()
        self.assertTrue(self.config.model.eye_awakening.scheduler.enable)

    def test_pending_recovery_reads_verified_map_without_adding_battle(self):
        directory = Path('log/EyeAwakening/oas_leveling')
        directory.mkdir(parents=True)
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        state = {'date': today, 'server': '测试服', 'status': '出错',
                 'accounts': {'小号一': {'battles': 4, 'progress': 49,
                                          'battle_pending': True}}}
        (directory / (today + '.json')).write_text(
            json.dumps(state, ensure_ascii=False), encoding='utf8')
        self.task.map_progress = lambda: 50
        with self.assertRaises(TaskEnd):
            self.task.run()
        entry = self.ledger()['accounts']['小号一']
        self.assertEqual(entry['battles'], 4)
        self.assertEqual(entry['progress'], 50)
        self.assertNotIn('battle_pending', entry)
        self.assertFalse(entry['recoveries'][0]['battle_count_added'])

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


class ActivityStoryRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.task = object.__new__(ScriptTask)
        self.task.device = NS(image=np.zeros((720, 1280, 3), dtype=np.uint8))

    def test_exact_toolbar_skip_click_uses_ocr_position(self):
        row = NS(ocr_text='跳过', box=np.array([[90, 20], [140, 20], [140, 48], [90, 48]]))
        with patch('tasks.EyeAwakening.script_task.RuleOcr') as reader, \
             patch.object(self.task, 'click', return_value=True) as click:
            reader.return_value.detect_and_ocr.return_value = [row]
            self.assertTrue(self.task.dismiss_activity_story())
        button = click.call_args.args[0]
        self.assertEqual(button.roi_front, (1210, 20, 50, 28))
        self.assertEqual(click.call_args.kwargs['interval'], 1.5)

    def test_unrelated_or_ambiguous_text_does_not_click(self):
        row = NS(ocr_text='跳过', box=np.array([[90, 20], [140, 20], [140, 48], [90, 48]]))
        for rows in ([], [NS(ocr_text='跳过剧情')], [row, row]):
            with patch('tasks.EyeAwakening.script_task.RuleOcr') as reader, \
                 patch.object(self.task, 'click') as click:
                reader.return_value.detect_and_ocr.return_value = rows
                self.assertFalse(self.task.dismiss_activity_story())
                click.assert_not_called()

    def test_inventory_return_skips_story_then_confirms_courtyard(self):
        with patch.object(self.task, 'screenshot'), \
             patch.object(self.task, 'appear', side_effect=[False, True]), \
             patch.object(self.task, 'dismiss_activity_story', return_value=True) as skip:
            self.task.leave_inventory()
        skip.assert_called_once()


class FireOneConnectionTest(unittest.TestCase):
    def test_selected_layer_waits_for_connection_without_retry_clicks(self):
        task = object.__new__(ScriptTask)
        task.device = NS(image=object(), click=lambda **kwargs: None)
        rows = [NS(ocr_text='壹层', box=np.array([[0, 0], [20, 20]]))]
        with patch.object(task, 'enter_map'), \
             patch.object(task, 'screenshot'), \
             patch.object(task, 'appear', return_value=True), \
             patch.object(task, 'connection_pending', side_effect=[False, True, True, False]), \
             patch.object(task, 'click') as click, \
             patch('tasks.EyeAwakening.script_task.RuleOcr') as reader, \
             patch('tasks.EyeAwakening.script_task.one_selected', return_value=True), \
             patch('tasks.EyeAwakening.script_task.time.sleep'):
            reader.return_value.detect_and_ocr.return_value = rows
            task.enter_fire_one()
        click.assert_not_called()

    def test_connection_labels(self):
        task = object.__new__(ScriptTask)
        task.device = NS(image=object())
        for text, expected in (('连接中......', True), ('正在连接：', True), ('挑战', False)):
            with self.subTest(text=text), patch('tasks.EyeAwakening.script_task.RuleOcr') as reader:
                reader.return_value.detect_and_ocr.return_value = [NS(ocr_text=text)]
                self.assertEqual(task.connection_pending(), expected)


class ReturnToMapTest(unittest.TestCase):
    def setUp(self):
        self.task = object.__new__(ScriptTask)
        self.task.device = NS(image=object())

    def test_connecting_overlay_prevents_back_click(self):
        with patch.object(self.task, 'screenshot'), \
             patch.object(self.task, 'map_visible', return_value=True), \
             patch.object(self.task, 'click') as click, \
             patch('tasks.EyeAwakening.script_task.RuleOcr') as reader, \
             patch('tasks.EyeAwakening.script_task.time.sleep'):
            reader.return_value.detect_and_ocr.side_effect = [[NS(ocr_text='正在连接')], []]
            self.task.return_to_map()
        click.assert_not_called()

    def test_unresponsive_back_is_bounded(self):
        with patch.object(self.task, 'screenshot'), \
             patch.object(self.task, 'map_visible', return_value=False), \
             patch.object(self.task, 'appear', return_value=True), \
             patch.object(self.task, 'click', return_value=True) as click, \
             patch('tasks.EyeAwakening.script_task.RuleOcr') as reader, \
             patch('tasks.EyeAwakening.script_task.time.sleep'):
            reader.return_value.detect_and_ocr.return_value = []
            with self.assertRaises(GameStuckError):
                self.task.return_to_map()
        self.assertEqual(click.call_count, 4)


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
