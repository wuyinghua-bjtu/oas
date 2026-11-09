import json
import unittest
from pathlib import Path

import numpy as np
from module.atom.image import RuleImage
from tasks.GameUi.assets import GameUiAssets
from tasks.KekkaiUtilize.assets import KekkaiUtilizeAssets


class GuildDetectionTests(unittest.TestCase):
    source = GameUiAssets.I_CHECK_GUILD
    front = (1072, 630, 49, 46)
    metadata = 'tasks/GameUi/page/page_img_3.json'
    item_name = 'check_guild'

    def rule(self):
        source = self.source
        return RuleImage(self.front, source.roi_back,
                         source.method, source.threshold, source.file)

    def test_small_offsets(self):
        for dx, dy in [(0, 0), (-3, 0), (-12, -12), (12, 12)]:
            with self.subTest(dx=dx, dy=dy):
                rule = self.rule()
                frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                fx, fy, width, height = self.front
                x, y = fx + dx, fy + dy
                frame[y:y + height, x:x + width] = rule.image
                self.assertTrue(rule.match(frame))
                self.assertEqual(rule.roi_front[:2], [x, y])

    def test_blank_and_unrelated_position_rejected(self):
        rule = self.rule()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.assertFalse(rule.match(frame))
        width, height = self.front[2:]
        frame[100:100 + height, 100:100 + width] = rule.image
        self.assertFalse(rule.match(frame))

    def test_generator_metadata_matches_runtime(self):
        records = json.loads(Path(self.metadata).read_text(encoding='utf-8'))
        record = next(row for row in records if row['itemName'] == self.item_name)
        self.assertEqual(tuple(map(int, record['roiBack'].split(','))), self.rule().roi_back)
        self.assertEqual(record['threshold'], 0.8)


class GuildRealmDetectionTests(GuildDetectionTests):
    source = KekkaiUtilizeAssets.I_GUILD_REALM
    front = (1065, 620, 67, 61)
    metadata = 'tasks/KekkaiUtilize/ku/image.json'
    item_name = 'guild_realm'


if __name__ == '__main__':
    unittest.main()
