import unittest
import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from module.exception import GameStuckError, ScriptEnd, TaskEnd
from tasks.EyeAwakening.progress import ProgressUncertain
from tasks.EyeExploration.script_task import ScriptTask, save_progress
from tasks.Exploration.base import Scene


class ProgressWriteTest(unittest.TestCase):
    def test_transient_windows_lock_retries_atomic_replace(self):
        error = PermissionError('locked')
        error.winerror = 32
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'progress.json'
            original_replace = Path.replace
            attempts = []
            def replace(temporary, destination):
                attempts.append(temporary)
                if len(attempts) < 3:
                    raise error
                return original_replace(temporary, destination)
            with patch.object(Path, 'replace', replace), \
                 patch('tasks.EyeExploration.script_task.time.sleep') as sleep:
                save_progress(target, {'progress': 45})
            self.assertEqual(json.loads(target.read_text(encoding='utf8'))['progress'], 45)
            self.assertEqual(len(set(attempts)), 1)
            self.assertEqual(sleep.call_count, 2)

    def test_persistent_denial_preserves_previous_file(self):
        error = PermissionError('denied')
        error.winerror = 5
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'progress.json'
            target.write_text('{"progress":44}', encoding='utf8')
            with patch.object(Path, 'replace', side_effect=error) as replace, \
                 patch('tasks.EyeExploration.script_task.time.sleep'):
                with self.assertRaises(PermissionError):
                    save_progress(target, {'progress': 45})
            self.assertEqual(replace.call_count, 6)
            self.assertEqual(json.loads(target.read_text(encoding='utf8'))['progress'], 44)
            self.assertEqual(len(list(Path(directory).glob('*.tmp'))), 1)

    def test_non_windows_permission_error_is_not_retried(self):
        with TemporaryDirectory() as directory:
            with patch.object(Path, 'replace', side_effect=PermissionError('denied')) as replace:
                with self.assertRaises(PermissionError):
                    save_progress(Path(directory) / 'progress.json', {'progress': 45})
            self.assertEqual(replace.call_count, 1)


class EyeExplorationTest(unittest.TestCase):
    def setUp(self):
        self.task = object.__new__(ScriptTask)
        self.task.device = NS(image=object())
        self.task.screenshot = lambda: None
        self.task.map_visible = lambda: True
        self.task.entry = {}
        self.task.save_state = lambda: None
        self.task.progress_current = 49
        self.task.minions_cnt = 1
        self.task.start_time = datetime.now()
        self.task.limit_time = timedelta(hours=2)
        self.task.original_config = NS(model=NS(eye_exploration=NS(options=NS(max_battles=5))))
        self.task.stop_reason = None
        self.task.__dict__['_config'] = NS(
            exploration_config=NS(minions_cnt=30), scrolls=NS(scrolls_enable=False))
        self.task.activate_realm_raid = Mock()

    def test_map_cap_stops_only_at_fifty(self):
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress', return_value=50):
            self.assertTrue(self.task.check_exit())
        self.assertEqual(self.task.stop_reason, '完成')
        self.assertEqual(self.task.entry['progress'], 50)

    def test_no_drop_keeps_farming(self):
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress', return_value=49):
            self.assertFalse(self.task.check_exit())
        self.assertIsNone(self.task.stop_reason)
        self.task.activate_realm_raid.assert_called_once_with(
            self.task._config.scrolls, self.task._config.exploration_config,
            resume_task='EyeExploration', submit_scrolls=False)

    def test_cap_does_not_switch_to_raid(self):
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress', return_value=50):
            self.assertTrue(self.task.check_exit())
        self.task.activate_realm_raid.assert_not_called()

    def test_normal_exploration_battle_limit_is_preserved(self):
        self.task._config.exploration_config.minions_cnt = 1
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress', return_value=49):
            self.assertTrue(self.task.check_exit())
        self.assertEqual(self.task.stop_reason, '探索战斗次数上限')
        self.task.activate_realm_raid.assert_not_called()

    def test_scheduler_updates_original_not_isolated_config(self):
        self.task.original_config.task_delay = Mock()
        self.task.config = NS(task_delay=Mock())
        self.task.set_next_run('EyeExploration', success=False, server=False, target=self.task.start_time)
        self.task.original_config.task_delay.assert_called_once_with(
            'EyeExploration', start_time=self.task.start_time, success=False,
            server=False, target=self.task.start_time)
        self.task.config.task_delay.assert_not_called()

    def run_with_mocked_handoff(self, directory, error):
        self.task.original_config.config_name = 'oas1'
        self.task.original_config.model.eye_exploration.scheduler = NS(enable=True)
        self.task.original_config.save = Mock()
        self.task.original_config.reload = Mock()
        self.task.appear = Mock(return_value=True)
        self.task.pre_process = Mock()
        self.task.run_solo = Mock(side_effect=error)
        with patch('tasks.EyeExploration.script_task.Path', return_value=Path(directory)), \
             patch('tasks.EyeExploration.script_task.NICK.ocr', return_value='test_character'), \
             patch('tasks.EyeExploration.script_task.EyeAwakeningTask.enter_map'), \
             patch('tasks.EyeExploration.script_task.time.sleep'):
            self.task.run()

    def test_raid_handoff_keeps_scheduler_enabled(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(TaskEnd):
                self.run_with_mocked_handoff(directory, TaskEnd())
            state = json.loads((Path(directory) / 'oas1' / (datetime.now().date().isoformat() + '.json'))
                               .read_text(encoding='utf8'))
        self.assertEqual(state['status'], '等待个人突破后继续')
        self.assertNotIn('failure', state)
        self.assertTrue(self.task.original_config.model.eye_exploration.scheduler.enable)
        self.task.original_config.save.assert_not_called()
        self.task.pre_process.assert_called_once()

    def test_real_failure_still_disables_scheduler(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(ScriptEnd):
                self.run_with_mocked_handoff(directory, GameStuckError('test_failure'))
        self.assertEqual(self.task.state['status'], '出错')
        self.assertFalse(self.task.original_config.model.eye_exploration.scheduler.enable)
        self.task.original_config.reload.assert_called_once()

    def test_chapter_entry_uses_last_confirmed_progress(self):
        self.task.map_visible = lambda: False
        self.task.appear = lambda rule: rule is self.task.I_E_EXPLORATION_CLICK
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress') as read_map:
            self.assertFalse(self.task.check_exit())
        read_map.assert_not_called()

    def test_battle_limit_is_not_reported_as_cap(self):
        self.task.minions_cnt = 5
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress', return_value=49):
            self.assertTrue(self.task.check_exit())
        self.assertEqual(self.task.stop_reason, '战斗次数上限')

    def test_reward_counter_requires_two_reads_before_click(self):
        phase = {'done': False, 'calls': 0}
        self.task.screenshot = lambda: None
        self.task.appear = lambda rule: not phase['done'] and rule is self.task.I_REWARD
        self.task.get_current_scene = lambda: Scene.MAIN if phase['done'] else Scene.UNKNOWN
        def click(*args, **kwargs):
            self.assertGreaterEqual(phase['calls'], 2)
            phase['done'] = True
        self.task.click = click
        def reward(image):
            phase['calls'] += 1
            return (50, 50)
        with patch('tasks.EyeExploration.script_task.read_drop_popup_quota', side_effect=ProgressUncertain()), \
             patch('tasks.EyeExploration.script_task.read_reward_quota', side_effect=reward), \
             patch('tasks.EyeExploration.script_task.time.sleep'):
            self.assertTrue(self.task.finish_battle_settlement(True))
        self.assertEqual(self.task.progress_current, 50)

    def test_failure_never_claims_success(self):
        with self.assertRaises(GameStuckError):
            self.task.finish_battle_settlement(False)


if __name__ == '__main__':
    unittest.main()
