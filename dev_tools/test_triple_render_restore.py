import ast
import unittest
from pathlib import Path
from unittest.mock import Mock


class RenderRestoreTests(unittest.TestCase):
    def run_restore(self, rectangles, iconic=False):
        source = ast.parse(Path('tasks/TripleAwakening/device.py').read_text(encoding='utf-8'))
        validate = next(node for node in ast.walk(source)
                        if isinstance(node, ast.FunctionDef) and node.name == 'validate')
        loop = next(node for node in validate.body if isinstance(node, ast.For))
        gui = Mock()
        gui.GetClientRect.side_effect = rectangles
        gui.GetWindowRect.return_value = (0, 0, 1288, 764)
        gui.IsIconic.return_value = iconic
        flags = Mock(SWP_NOMOVE=1, SWP_NOZORDER=2, SWP_NOACTIVATE=4)
        scope = {'win32gui': gui, 'win32con': flags, 'time': Mock(),
                 'RequestHumanTakeover': RuntimeError, 'root': 1, 'render': 2,
                 'info': {'name': 'member'}}
        exec(compile(ast.Module(body=[loop], type_ignores=[]), '<restore>', 'exec'), scope)
        return gui

    def test_exact_size_does_not_resize(self):
        gui = self.run_restore([(0, 0, 1280, 720)])
        gui.SetWindowPos.assert_not_called()

    def test_delayed_restore_rechecks_and_corrects_again(self):
        gui = self.run_restore([(0, 0, 1279, 719)] * 3 + [(0, 0, 1280, 720)])
        self.assertEqual(gui.SetWindowPos.call_count, 2)

    def test_unrestorable_size_stops_after_three_attempts(self):
        with self.assertRaises(RuntimeError):
            self.run_restore([(0, 0, 1279, 719)] * 7)

    def test_wrong_aspect_is_not_resized(self):
        with self.assertRaises(RuntimeError):
            self.run_restore([(0, 0, 800, 700)] * 7)


if __name__ == '__main__':
    unittest.main()
