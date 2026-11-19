import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from tasks.Component.SwitchSoul.switch_soul import SwitchSoul


class OptionalAudioTests(unittest.TestCase):
    def rows(self, title='式神音频扩展包下载', body='支持后台下载', labels=('取消',)):
        return [SimpleNamespace(ocr_text=text, box=np.array([[100, 280], [160, 280],
                                                           [160, 310], [100, 310]]))
                for text in (title, body, *labels)]

    def dismiss(self, rows):
        task = SimpleNamespace(device=Mock(image=object()))
        with patch('tasks.Component.SwitchSoul.switch_soul.RuleOcr') as reader, \
             patch('tasks.Component.SwitchSoul.switch_soul.sleep'):
            reader.return_value.detect_and_ocr.return_value = rows
            result = SwitchSoul.dismiss_optional_audio_download(task)
        return result, task.device

    def test_only_cancel_optional_audio(self):
        result, device = self.dismiss(self.rows())
        self.assertTrue(result)
        device.click.assert_called_once_with(530, 465, control_name='soul_optional_audio_cancel')

    def test_unrelated_dialog_is_untouched(self):
        result, device = self.dismiss(self.rows(title='购买资源'))
        self.assertFalse(result)
        device.click.assert_not_called()

    def test_ambiguous_cancel_is_untouched(self):
        result, device = self.dismiss(self.rows(labels=('取消', '取消')))
        self.assertFalse(result)
        device.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
