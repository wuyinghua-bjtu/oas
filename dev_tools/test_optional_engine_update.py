import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from tasks.base_task import BaseTask


class OptionalEngineUpdateTests(unittest.TestCase):
    def run_dialog(self, labels):
        task = SimpleNamespace(device=SimpleNamespace(
            image=np.full((720, 1280, 3), 255, dtype=np.uint8),
            click=Mock(), screenshot=Mock()))
        rows = [SimpleNamespace(ocr_text=label,
                                box=np.array([[100, 205], [135, 205], [135, 225], [100, 225]]))
                for label in labels]
        reader = Mock()
        reader.detect_and_ocr.return_value = rows
        with patch('tasks.base_task.RuleOcr', return_value=reader), patch('tasks.base_task.sleep'):
            handled = BaseTask.handle_optional_engine_update(task)
        return handled, task.device

    def test_ready_version_is_deferred(self):
        handled, device = self.run_dialog(['已经为您准备好了新版本，是否立即更新', '下次更新', '立即更新'])
        self.assertTrue(handled)
        device.click.assert_called_once_with(532, 445, control_name='ENGINE_UPDATE_NOT_NOW')

    def test_download_prompt_is_deferred(self):
        handled, device = self.run_dialog(['发现全新的引擎版本', '暂不更新', '后台下载'])
        self.assertTrue(handled)
        device.click.assert_called_once()

    def test_unrelated_and_mandatory_dialogs_are_not_clicked(self):
        for labels in (['下次更新', '立即更新'], ['已经为您准备好了新版本，是否立即更新', '立即更新']):
            handled, device = self.run_dialog(labels)
            self.assertFalse(handled)
            device.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
