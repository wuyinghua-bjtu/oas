import ast
from module.config.local_values import local_text
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / 'tasks/KekkaiUtilize/script_task.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8-sig'))
CLASS = next(node for node in TREE.body if isinstance(node, ast.ClassDef))


class SearchReturnTests(unittest.TestCase):
    def test_main_return_requires_two_fresh_menu_confirmations(self):
        source = SOURCE.parents[1] / 'GotoMain/script_task.py'
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        task_class = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        method = next(node for node in task_class.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'run')
        clock = SimpleNamespace(value=0)
        def advance(seconds):
            clock.value += seconds
        env = {'time': SimpleNamespace(monotonic=lambda: clock.value, sleep=advance),
               'logger': Mock(), 'page_main': 'main', 'TaskEnd': RuntimeError}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), env)
        task = SimpleNamespace(screenshot=Mock(),
                               _cancel_exit_dialog=Mock(return_value=False),
                               _main_menu_visible=Mock(side_effect=[False, True, True]),
                               device=SimpleNamespace(app_is_running=Mock(return_value=True)),
                               appear_then_click=Mock(return_value=True),
                               I_UI_BACK_YELLOW='yellow', I_UI_BACK_BLUE='blue', I_UI_BACK_RED='red')
        with self.assertRaisesRegex(RuntimeError, 'Goto main verified'):
            env['run'](task)
        self.assertEqual(task.screenshot.call_count, 3)
        self.assertEqual(task.ui_current, 'main')

    def test_named_branch_never_uses_unrestricted_scan(self):
        run = next(node for node in CLASS.body if isinstance(node, ast.FunctionDef)
                   and node.name == 'run_utilize')
        branch = next(node for node in run.body if isinstance(node, ast.If)
                      and isinstance(node.test, ast.Name) and node.test.id == 'target_names')
        calls = [node.func.attr for node in ast.walk(branch)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        self.assertNotIn('_current_select_best', calls)
        self.assertIn('_select_search_result_card', calls)
        groups = [node for node in ast.walk(branch) if isinstance(node, ast.For)
                  and isinstance(node.target, ast.Name) and node.target.id == 'friend_list']
        self.assertEqual(ast.unparse(groups[0].iter), '(SelectFriendList.DIFFERENT_SERVER,)')

    def test_legacy_selection_only_runs_without_search_names(self):
        run = next(node for node in CLASS.body if isinstance(node, ast.FunctionDef)
                   and node.name == 'run_utilize')
        loops = [node for node in run.body if isinstance(node, ast.While)
                 and any(isinstance(child, ast.Call)
                         and isinstance(child.func, ast.Attribute)
                         and child.func.attr == '_current_select_best'
                         for child in ast.walk(node))]
        self.assertEqual(len(loops), 1)
        self.assertEqual(ast.unparse(loops[0].test), 'not target_names')

    def test_failed_search_does_not_fall_back_to_legacy_selection(self):
        run = next(node for node in CLASS.body if isinstance(node, ast.FunctionDef)
                   and node.name == 'run_utilize')
        prefix = []
        for statement in run.body:
            if isinstance(statement, ast.While):
                break
            prefix.append(statement)
        method = ast.FunctionDef(name='search_only', args=run.args, body=prefix,
                                 decorator_list=[])
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        friend_lists = SimpleNamespace(SAME_SERVER='same_server',
                                       DIFFERENT_SERVER='different_server')
        env = {'logger': Mock(), 'SelectFriendList': friend_lists,
               'ShikigamiClass': SimpleNamespace(N='N')}
        exec(compile(module, str(SOURCE), 'exec'), env)
        task = SimpleNamespace(
            config=SimpleNamespace(kekkai_utilize=SimpleNamespace(
                utilize_config=SimpleNamespace(target_friend_names='alice,bob'))),
            _search_friend_by_name=Mock(return_value=False),
            _current_select_best=Mock(side_effect=AssertionError('Legacy scan used')),
            switch_friend_list=Mock(side_effect=AssertionError('Legacy navigation used')))
        self.assertFalse(env['search_only'](task))
        self.assertEqual(task._utilize_retry_delay, 180)
        self.assertEqual(task._search_friend_by_name.call_count, 2)
        task._search_friend_by_name.assert_any_call('alice', 'different_server')
        task._search_friend_by_name.assert_any_call('bob', 'different_server')
        task._current_select_best.assert_not_called()
        task.switch_friend_list.assert_not_called()

    def return_task(self, ready=False):
        method = next(node for node in CLASS.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'back_realm')
        clock = SimpleNamespace(value=0)
        def sleep(seconds):
            clock.value += seconds
        env = {'time': SimpleNamespace(monotonic=lambda: clock.value, sleep=sleep),
               'logger': Mock(), 'page_main': SimpleNamespace(check_button='main'),
               'page_guild': SimpleNamespace(check_button='guild')}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), env)
        task = SimpleNamespace(screenshot=Mock(), appear=Mock(return_value=ready),
                               appear_multi_scale=Mock(return_value=False),
                               appear_then_click=Mock(return_value=False),
                               I_REALM_SHIN='realm', I_SHI_DEFENSE='defense',
                               I_RS_RECORDS_SHIKI='growth', O_UTILIZE_FRIEND_LIST_TITLE='friends',
                               I_UI_BACK_RED='red', I_UI_BACK_BLUE='blue',
                               device=SimpleNamespace(app_is_running=Mock(return_value=True),
                                   active_app_display_id=Mock(return_value=2), adb_shell=Mock()))
        return env['back_realm'], task, clock

    def test_search_keyboard_uses_verified_default_focus(self):
        method = next(node for node in CLASS.body if isinstance(node, ast.FunctionDef)
                      and node.name == '_search_friend_by_name')
        commands = [ast.literal_eval(node.args[0]) for node in ast.walk(method)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'adb_shell' and node.args
                    and isinstance(node.args[0], ast.List)
                    and all(isinstance(item, ast.Constant) for item in node.args[0].elts)]
        self.assertIn(['dumpsys', 'window'], commands)
        self.assertIn(['input', 'keyevent', '123'], commands)
        self.assertNotIn("'input', '-d'", ast.unparse(method))
        self.assertIn(['dumpsys', 'input_method'], commands)
        retries = [node for node in ast.walk(method) if isinstance(node, ast.For)
                   and ast.unparse(node.iter) == 'range(3)']
        self.assertEqual(len(retries), 1)
        self.assertTrue(retries[0].orelse)

    def test_same_name_results_skip_unusable_first_card(self):
        method = next(node for node in CLASS.body if isinstance(node, ast.FunctionDef)
                      and node.name == '_select_search_result_card')
        rows = [SimpleNamespace(ocr_text=local_text('LOCAL_PARTNER'),
                                box=[(20, position), (60, position),
                                     (60, position + 20), (20, position + 20)])
                for position in (20, 100)]
        reader = SimpleNamespace(detect_and_ocr=Mock(return_value=rows))
        env = {'RuleOcr': Mock(return_value=reader), 'time': SimpleNamespace(sleep=Mock())}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), env)
        task = SimpleNamespace(screenshot=Mock(), device=SimpleNamespace(image=None, click=Mock()),
                               _friend_search_text=Mock(return_value=local_text('LOCAL_PARTNER')),
                               check_card_num=Mock(side_effect=[('unknown', 0), ('斗鱼', 143)]))
        self.assertTrue(env['_select_search_result_card'](task, local_text('LOCAL_PARTNER')))
        self.assertEqual(task.device.click.call_count, 2)
        self.assertEqual(task.ap_max_num, 143)

    def test_unknown_return_is_bounded(self):
        method, task, clock = self.return_task()
        self.assertFalse(method(task))
        self.assertLessEqual(clock.value, 25)
        self.assertEqual(task.device.adb_shell.call_count, 3)
        task.device.adb_shell.assert_called_with(['input', '-d', '2', 'keyevent', '4'])

    def test_known_destination_needs_no_back(self):
        method, task, clock = self.return_task(True)
        self.assertTrue(method(task))
        task.device.adb_shell.assert_not_called()

    def test_own_growth_page_needs_no_navigation(self):
        method, task, clock = self.return_task()
        task.appear.side_effect = lambda marker: marker == 'growth'
        self.assertTrue(method(task))
        task.device.adb_shell.assert_not_called()

    def test_stopped_game_is_not_started(self):
        method, task, clock = self.return_task()
        task.device.app_is_running.return_value = False
        self.assertFalse(method(task))
        task.device.adb_shell.assert_not_called()


if __name__ == '__main__':
    unittest.main()
