import unittest

from tasks.WantedQuests.script_task import current_detail_goto_buttons, normalize_wanted_route_type, parse_wanted_route


class WantedDetailRoutesTests(unittest.TestCase):
    def test_current_button_fits_search_region(self):
        for button in current_detail_goto_buttons():
            front_x, front_y, width, height = button.roi_front
            back_x, back_y, back_width, back_height = button.roi_back
            self.assertGreaterEqual(front_x, back_x)
            self.assertGreaterEqual(front_y, back_y)
            self.assertLessEqual(front_x + width, back_x + back_width)
            self.assertLessEqual(front_y + height, back_y + back_height)

    def test_route_quantity_with_missing_closing_bracket(self):
        for text in ('第七章(数量：7', '第七章（数量：7）', '第七章(数量:7)'):
            with self.subTest(text=text):
                self.assertEqual(parse_wanted_route(text), ('第七章', 7))

    def test_invalid_or_partial_quantity_rejected(self):
        for text in ('第七章', '第七章(数量:)', '第七章(数量:0)',
                     '(数量:7)', '第七章(数量:7)其它', '第七章(数量:7x'):
            with self.subTest(text=text):
                self.assertIsNone(parse_wanted_route(text))

    def test_recorded_trailing_ocr_punctuation(self):
        self.assertEqual(parse_wanted_route('海怪的温柔·肆（数量：4）、'), ('海怪的温柔·肆', 4))

    def test_recorded_interleaved_trailing_whitespace(self):
        for text in ('第二十七章(数量：8）　。', '第二十七章(数量：8） 、　。 ',
                     '第二十七章(数量：8）\t， \n'):
            with self.subTest(text=text):
                self.assertEqual(parse_wanted_route(text), ('第二十七章', 8))

    def test_recorded_route_types(self):
        for text, expected in (('式神石', '式神'), ('|探索', '探索'), ('｜ 探索 ', '探索'),
                               ('闻', '秘闻'), ('挑战', '式神'), ('秘闻', '秘闻')):
            with self.subTest(text=text):
                self.assertEqual(normalize_wanted_route_type(text), expected)

    def test_recorded_duplicate_closing_bracket(self):
        self.assertEqual(parse_wanted_route('第六章(数量：9））'), ('第六章', 9))

    def test_unknown_route_types_are_not_guessed(self):
        for text in ('气', '未知', '探索石'):
            with self.subTest(text=text):
                self.assertEqual(normalize_wanted_route_type(text), text)


if __name__ == '__main__':
    unittest.main()
