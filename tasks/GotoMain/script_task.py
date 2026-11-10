# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main
from module.exception import TaskEnd
from module.atom.ocr import RuleOcr
from module.logger import logger
import time


class ScriptTask(GameUi):

    def _main_menu_visible(self):
        reader = RuleOcr(roi=(0, 570, 1280, 150), area=(0, 570, 1280, 150),
                         mode='Full', method='Default', keyword='', name='goto_main_menu')
        text = ''.join(str(result.ocr_text) for result in reader.detect_and_ocr(self.device.image))
        return sum(label in text for label in ('图鉴', '组队', '阴阳寮', '商店', '花合战',
                                                '好友', '式神录', '阴阳术')) >= 3

    def _cancel_exit_dialog(self):
        roi = (350, 230, 580, 260)
        reader = RuleOcr(roi=roi, area=roi, mode='Full', method='Default',
                         keyword='', name='goto_main_exit_dialog')
        results = reader.detect_and_ocr(self.device.image)
        if not any('退出游戏' in str(result.ocr_text) for result in results):
            return False
        for result in results:
            if str(result.ocr_text).strip() == '取消':
                position = (int(sum(point[0] for point in result.box) / 4 + roi[0]),
                            int(sum(point[1] for point in result.box) / 4 + roi[1]))
                self.device.click(*position, control_name='GOTO_MAIN_CANCEL_EXIT')
                return True
        return False

    def run(self) -> None:
        started = time.monotonic()
        confirmed = 0
        last_back = started - 3
        back_count = 0
        while time.monotonic() - started < 35:
            self.screenshot()
            if self._cancel_exit_dialog():
                confirmed = 0
                time.sleep(0.5)
                continue
            if self._main_menu_visible():
                confirmed += 1
                if confirmed >= 2:
                    self.ui_current = page_main
                    logger.info('Main courtyard verified by bottom menu on two fresh frames')
                    raise TaskEnd('Goto main verified')
                time.sleep(0.5)
                continue
            confirmed = 0
            now = time.monotonic()
            if back_count < 6 and now - last_back >= 3:
                if not self.device.app_is_running():
                    raise TaskEnd('Goto main unconfirmed: game is not running')
                clicked = False
                for button in (self.I_UI_BACK_YELLOW, self.I_UI_BACK_BLUE, self.I_UI_BACK_RED):
                    if self.appear_then_click(button, interval=1):
                        clicked = True
                        break
                if not clicked:
                    self.device.adb_shell(['input', '-d', str(self.device.active_app_display_id()),
                                           'keyevent', '4'])
                back_count += 1
                last_back = now
            time.sleep(0.5)
        logger.warning('Main courtyard not verified after bounded return recovery')
        raise TaskEnd('Goto main unconfirmed; no success reported')
