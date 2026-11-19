import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.WantedQuests.explore import WQExplore, ExploreWantedBoss
from tasks.Exploration.base import Scene

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
                               ('闻', '秘闻'), ('挑战', '式神'), ('秘闻', '秘闻'),
                               ('［探索', '探索'), ('探探索', '探索')):
            with self.subTest(text=text):
                self.assertEqual(normalize_wanted_route_type(text), expected)

    def test_recorded_duplicate_closing_bracket(self):
        self.assertEqual(parse_wanted_route('第六章(数量：9））'), ('第六章', 9))

    def test_unknown_route_types_are_not_guessed(self):
        for text in ('气', '未知', '探索石'):
            with self.subTest(text=text):
                self.assertEqual(normalize_wanted_route_type(text), text)

    def test_anmeng_is_excluded_at_every_floor(self):
        for floor in ('壹', '伍', '拾', '番外'):
            with self.subTest(floor=floor):
                self.assertIsNone(parse_wanted_route(f'安梦奇缘·{floor}(数量:3)'))
        self.assertIsNone(parse_wanted_route('安 梦奇缘·伍(数量:3)'))

    def test_other_routes_remain_available(self):
        for destination in ('第二十五章', '海怪的温柔·肆'):
            with self.subTest(destination=destination):
                self.assertEqual(parse_wanted_route(f'{destination}(数量:3)'), (destination, 3))

    def test_missing_highlight_stops_before_click_guard(self):
        task = object.__new__(WQExplore)
        task.config = SimpleNamespace(model=SimpleNamespace(global_game=SimpleNamespace(
            costume_config=SimpleNamespace(costume_main_type=None))))
        task.device = SimpleNamespace(image=None, save_screenshot=Mock())
        task.__dict__['TEMPLATE_GIF'] = Mock()
        task.__dict__['_match_end'] = Mock(stable=Mock(return_value=True))
        task.screenshot = Mock()
        task.appear = Mock(side_effect=lambda image: image is task.I_UI_BACK_YELLOW or image is task.I_E_EXPLORATION_CLICK)
        task.get_current_scene = Mock(return_value=Scene.MAIN)
        task.swipe = Mock(return_value=None)
        task.quit_explore = Mock()
        task.fire = Mock()
        with patch('tasks.WantedQuests.explore.Timer') as timer:
            timer.return_value.reached.return_value = True
            with self.assertRaises(ExploreWantedBoss):
                task.explore(Mock(), 4)
        self.assertEqual(task.swipe.call_count, 6)
        task.quit_explore.assert_called_once()
        task.fire.assert_not_called()

    def test_successful_sweep_returns_to_verify_progress(self):
        task = object.__new__(WQExplore)
        task.config = SimpleNamespace(model=SimpleNamespace(global_game=SimpleNamespace(
            costume_config=SimpleNamespace(costume_main_type=None))))
        task.device = SimpleNamespace(image=None, save_screenshot=Mock())
        task.__dict__['TEMPLATE_GIF'] = Mock()
        task.screenshot = Mock()
        target = task.TEMPLATE_GIF
        matched = iter([True] + [False] * 8)
        task.appear = Mock(side_effect=lambda asset: next(matched) if asset is target else
                           asset is task.I_UI_BACK_YELLOW or asset is task.I_E_EXPLORATION_CLICK)
        task.get_current_scene = Mock(return_value=Scene.MAIN)
        task.swipe = Mock(return_value=None)
        task.quit_explore = Mock()
        task.fire = Mock(return_value=True)
        task.ui_get_current_page = Mock()
        task.ui_click_until_disappear = Mock()
        task.ui_goto = Mock(return_value=True)
        task.minions_cnt = 1
        with patch('tasks.WantedQuests.explore.Timer') as timer:
            timer.return_value.reached.return_value = True
            task.explore(Mock(), 4)
        task.quit_explore.assert_called_once()
        task.ui_goto.assert_called_once()


if __name__ == '__main__':
    unittest.main()
