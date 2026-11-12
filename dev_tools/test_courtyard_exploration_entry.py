import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from tasks.GameUi.game_ui import GameUi


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
