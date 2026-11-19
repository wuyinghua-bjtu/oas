import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from tasks.GroupedAwakening.post_guild import material_selection


class MaterialRowsTests(unittest.TestCase):
    def rows(self, counts):
        result = [SimpleNamespace(ocr_text=text, box=np.array([[500, 10]] * 4))
                  for text in ('业火轮', '风转符', '水灵鲤', '天雷鼓', '提交')]
        for height, count in zip((106, 228, 350, 474), counts):
            result.append(SimpleNamespace(ocr_text=count, box=np.array([[170, height]] * 4)))
        return result

    def test_sums_four_verified_material_rows(self):
        with patch('tasks.GroupedAwakening.post_guild._words', return_value=''), \
                patch('tasks.GroupedAwakening.post_guild.RuleOcr') as reader:
            reader.return_value.detect_and_ocr.return_value = self.rows(['2/9', '0/0', '3/6', '0/10'])
            self.assertEqual(material_selection(Mock()), 5)

    def test_missing_or_impossible_count_is_not_zero(self):
        for counts in (['0/9', '0/0', '0/6'], ['10/9', '0/0', '0/6', '0/10']):
            with patch('tasks.GroupedAwakening.post_guild._words', return_value=''), \
                    patch('tasks.GroupedAwakening.post_guild.RuleOcr') as reader:
                reader.return_value.detect_and_ocr.return_value = self.rows(counts)
                self.assertIsNone(material_selection(Mock()))


if __name__ == '__main__':
    unittest.main()
