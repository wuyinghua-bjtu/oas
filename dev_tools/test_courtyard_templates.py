import unittest
from unittest.mock import patch

import numpy as np

from tasks.GameUi.courtyard_templates import CourtyardTemplateAssets


class CourtyardTemplateTests(unittest.TestCase):
    def test_three_distinct_menu_entries_required(self):
        rules = CourtyardTemplateAssets.get_templates()
        names = [name for name in rules if name.startswith('main_goto_')][:3]
        self.assertEqual(len(names), 3)
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        for index, name in enumerate(names):
            rule = rules[name]
            left, top, width, height = rule.roi_front
            frame[top:top + height, left:left + width] = rule.image
            self.assertEqual(CourtyardTemplateAssets.menu_visible(frame), index == 2)

    def test_blank_and_wrong_resolution_rejected(self):
        self.assertFalse(CourtyardTemplateAssets.menu_visible(np.zeros((720, 1280, 3), dtype=np.uint8)))
        self.assertFalse(CourtyardTemplateAssets.menu_visible(np.zeros((717, 1274, 3), dtype=np.uint8)))

    def test_missing_local_templates_fall_back(self):
        with patch.object(CourtyardTemplateAssets, 'templates', {}):
            self.assertFalse(CourtyardTemplateAssets.menu_visible(np.zeros((720, 1280, 3), dtype=np.uint8)))


if __name__ == '__main__':
    unittest.main()
