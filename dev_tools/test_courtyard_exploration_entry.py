import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_awake_zones, page_exploration
from module.exception import GameStuckError
from tasks.EvoZone.config import Layer


class CourtyardExplorationEntryTests(unittest.TestCase):
    def setUp(self):
        self.task = GameUi.__new__(GameUi)
        self.task.device = Mock(image=np.zeros((720, 1280, 3), dtype=np.uint8))
        self.task.I_CHECK_EXPLORATION = Mock()
        self.task.I_CHECK_EXPLORATION.match.return_value = False
        self.task.I_CHECK_MAIN = Mock()
        self.task.I_CHECK_MAIN.match.return_value = True
        self.label = SimpleNamespace(
            ocr_text='探索', box=np.array([[260, 45], [300, 45], [300, 65], [260, 65]]))
        self.reader_patch = patch('tasks.GameUi.game_ui.RuleOcr')
        self.reader = self.reader_patch.start().return_value
        self.reader.detect_and_ocr.return_value = [self.label]
        self.addCleanup(self.reader_patch.stop)

    def test_clicks_unique_label_on_verified_courtyard(self):
        self.assertTrue(self.task._click_exploration_label())
        self.task.device.screenshot.assert_called_once()
        self.task.device.click.assert_called_once_with(
            523, 155, control_name='courtyard_exploration_label')

    def test_rejects_exploration_page(self):
        self.task.I_CHECK_EXPLORATION.match.return_value = True
        self.assertFalse(self.task._click_exploration_label())
        self.reader.detect_and_ocr.assert_not_called()
        self.task.device.click.assert_not_called()

    @patch('tasks.GameUi.courtyard_templates.CourtyardTemplateAssets.menu_visible', return_value=False)
    def test_rejects_unverified_page(self, menu_visible):
        self.task.I_CHECK_MAIN.match.return_value = False
        self.assertFalse(self.task._click_exploration_label())
        self.task.device.click.assert_not_called()

    @patch('tasks.GameUi.courtyard_templates.CourtyardTemplateAssets.menu_visible', return_value=True)
    def test_accepts_verified_alternate_courtyard(self, menu_visible):
        self.task.I_CHECK_MAIN.match.return_value = False
        self.assertTrue(self.task._click_exploration_label())

    def test_rejects_missing_ambiguous_or_partial_labels(self):
        for items in ([], [self.label, self.label], [SimpleNamespace(ocr_text='妖气探索')]):
            with self.subTest(items=items):
                self.reader.detect_and_ocr.return_value = items
                self.assertFalse(self.task._click_exploration_label())
        self.task.device.click.assert_not_called()

    def test_rejects_coordinates_outside_entry_region(self):
        self.label.box = np.array([[1000, 45], [1040, 45], [1040, 65], [1000, 65]])
        self.assertFalse(self.task._click_exploration_label())
        self.task.device.click.assert_not_called()


class GroupedEntryNavigationTests(unittest.TestCase):
    def run_entry(self, participant):
        source = Path(__file__).resolve().parents[1] / 'tasks/GroupedAwakening/script_task.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        loop = next(node for node in ast.walk(tree) if isinstance(node, ast.For)
                    and any(isinstance(child, ast.Constant) and isinstance(child.value, str)
                            and child.value.startswith('首场取消阵容锁定 ')
                            for child in ast.walk(node))
                    and isinstance(node.target, ast.Name) and node.target.id == 'participant')
        module = ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[]))
        exec(compile(module, str(source), 'exec'), {
            'active': [participant], 'page_exploration': page_exploration,
            'page_awake_zones': page_awake_zones, 'Layer': Layer,
            'GameStuckError': GameStuckError,
        })

    def test_confirmed_navigation_enters_and_unlocks(self):
        participant = Mock(expected_name='test')
        self.run_entry(participant)
        self.assertEqual([call.args[0] for call in participant.ui_goto.call_args_list],
                         [page_exploration, page_awake_zones])
        participant.evozone_enter.assert_called_once()
        participant.check_lock.assert_called_once_with(False)

    def test_failed_navigation_never_enters_or_unlocks(self):
        for results in ([False], [True, False]):
            with self.subTest(results=results):
                participant = Mock(expected_name='test')
                participant.ui_goto.side_effect = results
                with self.assertRaises(GameStuckError):
                    self.run_entry(participant)
                participant.evozone_enter.assert_not_called()
                participant.check_lock.assert_not_called()


class TeamCreationNavigationTests(unittest.TestCase):
    def test_navigation_failure_stops_before_dungeon_or_room_actions(self):
        source = Path(__file__).resolve().parents[1] / 'tasks/TripleAwakening/script_task.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == 'create_team')
        # Execute the real navigation prefix without importing live-device code.
        prefix = method.body[:next(i for i, node in enumerate(method.body)
                                   if isinstance(node, ast.Expr)
                                   and isinstance(node.value, ast.Call)
                                   and getattr(node.value.func, 'attr', '') == 'evozone_enter') + 1]
        module = ast.fix_missing_locations(ast.Module(body=prefix, type_ignores=[]))
        for results in ([False], [True, False]):
            with self.subTest(results=results):
                leader = Mock()
                leader.ui_goto.side_effect = results
                with self.assertRaises(GameStuckError):
                    exec(compile(module, str(source), 'exec'), {
                        'leader': leader, 'page_exploration': page_exploration,
                        'page_awake_zones': page_awake_zones,
                        'GameStuckError': GameStuckError,
                    })
                leader.evozone_enter.assert_not_called()
        leader = Mock()
        exec(compile(module, str(source), 'exec'), {
            'leader': leader, 'page_exploration': page_exploration,
            'page_awake_zones': page_awake_zones, 'GameStuckError': GameStuckError,
        })
        self.assertEqual([call.args[0] for call in leader.ui_goto.call_args_list],
                         [page_exploration, page_awake_zones])
        leader.evozone_enter.assert_called_once()


class MentorshipControlTests(unittest.TestCase):
    def test_mentorship_uses_matching_adb_capture_and_input(self):
        source = Path(__file__).resolve().parents[1] / 'tasks/Mentorship/script_task.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        assignments = [node for node in ast.walk(tree)
                       if isinstance(node, ast.Assign)
                       and isinstance(node.targets[0], ast.Tuple)
                       and [getattr(item, 'attr', '') for item in node.targets[0].elts]
                       == ['screenshot_method', 'control_method']]
        self.assertEqual(len(assignments), 1)
        self.assertEqual(ast.literal_eval(assignments[0].value), ('ADB', 'ADB'))

    def test_unknown_assist_does_not_click_guessed_lineup_positions(self):
        source = Path(__file__).resolve().parents[1] / 'tasks/Mentorship/apprentice_souls.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        controls = [node.value for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        self.assertNotIn('mentorship_open_lineup', controls)


if __name__ == '__main__':
    unittest.main()
