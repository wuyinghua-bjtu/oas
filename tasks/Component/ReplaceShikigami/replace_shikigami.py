# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from module.atom.ocr import RuleOcr
from module.atom.image import RuleImage
from module.base.timer import Timer
from module.logger import logger

from tasks.base_task import BaseTask
from tasks.Utils.config_enum import ShikigamiClass
from tasks.Component.ReplaceShikigami.assets import ReplaceShikigamiAssets
import time
from module.exception import GameStuckError
from win32api import MAKELONG
from win32con import (HTCLIENT, MK_LBUTTON, WM_LBUTTONDOWN, WM_LBUTTONUP,
                      WM_MOUSEMOVE, WM_NCHITTEST, WM_SETCURSOR)
from win32gui import PostMessage, SendMessage
class ReplaceShikigami(BaseTask, ReplaceShikigamiAssets):

    O_RS_ALL_SELECTED = RuleOcr(
        roi=(15, 615, 90, 70), area=(15, 615, 90, 70),
        mode='Full', method='Default', keyword='全部', name='rs_all_selected')

    def in_shikigami_growth(self, screenshot=False) -> bool:
        # The generic growth page is shared by the player's own realm and the
        # friend foster picker, so the records icon is the common page marker.
        if screenshot:
            self.screenshot()
        return self.appear(self.I_RS_RECORDS_SHIKI, interval=0.5)

    def in_foster_selection(self, screenshot=False) -> bool:
        """Return whether the current page is the friend foster picker.

        The records icon alone is not distinctive enough: on some realm-result
        backgrounds it can produce a false template match.  The picker has
        either a selected rarity marker or the default ``全部`` filter.
        """
        if screenshot:
            self.screenshot()
        if not self.appear(self.I_RS_RECORDS_SHIKI):
            return False
        selected_markers = (
            self.I_RS_MATERIAL_SELECTED,
            self.I_RS_N_SELECTED,
            self.I_RS_R_SELECTED,
            self.I_RS_SR_SELECTED,
            self.I_RS_SSR_SELECTED,
            self.I_RS_SP_SELECTED,
            self.I_RS_UR_SELECTED,
        )
        if any(self.appear(marker) for marker in selected_markers):
            return True
        return bool(self.O_RS_ALL_SELECTED.ocr(self.device.image))

    def switch_shikigami_class(self, shikigami_class: ShikigamiClass = ShikigamiClass.N):
        """
        要求在式神育成的界面
        切换分类
        :param shikigami_class:
        :param shikigami_order:
        :return:
        """
        match_selected = {ShikigamiClass.MATERIAL: self.I_RS_MATERIAL_SELECTED,
                          ShikigamiClass.N: self.I_RS_N_SELECTED,
                          ShikigamiClass.R: self.I_RS_R_SELECTED,
                          ShikigamiClass.SR: self.I_RS_SR_SELECTED,
                          ShikigamiClass.SSR: self.I_RS_SSR_SELECTED,
                          ShikigamiClass.SP: self.I_RS_SP_SELECTED,
                          ShikigamiClass.UR: self.I_RS_UR_SELECTED}
        match_click = {ShikigamiClass.MATERIAL: self.I_RS_MATERIAL,
                       ShikigamiClass.N: self.I_RS_N,
                       ShikigamiClass.R: self.I_RS_R,
                       ShikigamiClass.SR: self.I_RS_SR,
                       ShikigamiClass.SSR: self.I_RS_SSR,
                       ShikigamiClass.SP: self.I_RS_SP,
                       ShikigamiClass.UR: self.I_RS_UR}
        check_selected = match_selected[shikigami_class]
        check_click = match_click[shikigami_class]
        # 选择式神的种类
        while 1:
            self.screenshot()

            if self.appear(check_selected):
                break
            if self.appear(check_click, interval=1):
                if not (self.wait_until_pos_stable(check_click, stable_time=1.5, timeout=3.5)
                        and self.appear(check_click)):
                    continue
                if self.appear(check_selected):
                    break
                self.click(check_click, interval=2)
                continue
            self.wait_animate_stable(rule=self.C_SHIKIGAMI_SWITCH_1, interval=0.8)
            if self.click(self.C_SHIKIGAMI_SWITCH_1, interval=3.5):
                continue
        logger.info('Select shikigami class: %s' % shikigami_class)

    def unset_shikigami_max_lv(self):
        """
        要求在式神育成的界面
        拉下满级的式神，留空位置
        :return:
        """
        while 1:
            self.screenshot()
            if not self.appear(self.I_RS_LEVEL_MAX):
                break
            else:
                self.appear_then_click(self.I_RS_LEVEL_MAX, interval=0.5)
        logger.info('Unset all shikigami max lv')

    def set_shikigami(self, shikigami_order: int = 7,
                      stop_image: RuleImage = None,
                      require_confirmation: bool = False):
        """
        要求在式神育成的界面
        选择式神 1-7
        :param stop_image:  结束的图片，如果不出现就结束
        :param shikigami_order:
        :param require_confirmation: 必须实际点击寄养确认按钮并确认弹窗关闭
        :return:
        """
        # 选择式神
        _click_match = {1: self.C_SHIKIGAMI_LEFT_1,
                        2: self.C_SHIKIGAMI_LEFT_2,
                        3: self.C_SHIKIGAMI_LEFT_3,
                        4: self.C_SHIKIGAMI_LEFT_4,
                        5: self.C_SHIKIGAMI_LEFT_5,
                        6: self.C_SHIKIGAMI_LEFT_6,
                        7: self.C_SHIKIGAMI_LEFT_7}
        click_match = _click_match[shikigami_order]
        TIMEOUT_SEC = 120          # 超时时长（秒）
        start_time = time.time()   # 记录起始时间
        click_interval_timer = Timer(1.5).start()  # 点击选择式神间隔
        confirmation_wait = None
        clicked = False
        while 1:
            # ——1. 先做超时检查——
            if time.time() - start_time > TIMEOUT_SEC:
                logger.error('寄养等待超过 2 分钟，自动退出')
                raise GameStuckError('寄养超时（>120 s）')
            # 恢复点击操作
            if click_interval_timer.reached_and_reset():
                clicked = False
            
            self.screenshot()

            stop_visible = self.appear(stop_image)

            # The current and legacy foster-confirm buttons differ slightly
            # in color/antialiasing. Both are confined to the same small ROI;
            # 0.75 recognizes both without widening the click area.
            if self.appear(self.I_U_CONFIRM_SMALL, threshold=0.75):
                x, y = 737, 543
                try:
                    # MuMu ignores window messages on this modal. The game can
                    # run on a secondary Android display, so address that
                    # display explicitly for this single tap.
                    display_id = self.device.tap_active_app_display(x, y)
                    method = f'adb display {display_id} tap'
                except Exception as error:
                    logger.warning('ADB display confirm click unavailable: %s', error)
                    handle = self.device.control_handle_list[1]
                    pos = MAKELONG(x, y)
                    SendMessage(handle, WM_NCHITTEST, 0, pos)
                    SendMessage(handle, WM_SETCURSOR, handle,
                                MAKELONG(HTCLIENT, WM_LBUTTONDOWN))
                    PostMessage(handle, WM_MOUSEMOVE, 0, pos)
                    PostMessage(handle, WM_LBUTTONDOWN, MK_LBUTTON, pos)
                    time.sleep(0.15)
                    PostMessage(handle, WM_LBUTTONUP, 0, pos)
                    method = 'full window-message sequence'
                self.device.click_record_add(self.I_U_CONFIRM_SMALL.name)
                logger.info('Click ( 737,  543) @ %s (%s)',
                            self.I_U_CONFIRM_SMALL.name, method)
                time.sleep(1.5)
                self.screenshot()
                if not self.appear(self.I_U_CONFIRM_SMALL, threshold=0.75):
                    logger.info('Foster confirmation dialog closed')
                    return True
                clicked = False  # 点击了确认, 恢复选式神的操作
                continue

            # Selecting a foster shikigami can hide the list marker one frame
            # before the confirmation modal appears.  In the foster flow that
            # transition is not success: wait briefly for the real confirm
            # button and fail cleanly if it never arrives.
            if require_confirmation and confirmation_wait is not None:
                if confirmation_wait.reached():
                    logger.warning('Foster confirmation did not appear after selecting shikigami')
                    return False
                time.sleep(0.2)
                continue

            if not stop_visible:
                if require_confirmation:
                    logger.warning('Foster selection page disappeared before confirmation')
                    return False
                break

            # 是否育成候补式神按钮
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1) or self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1):
                continue
            # 与下方点击第7个式神操作互斥, 防止确认按钮还没有出现被下方取消掉
            if not clicked and self.click(click_match, interval=1.5):
                clicked = True
                if require_confirmation:
                    confirmation_wait = Timer(10).start()
                continue
            if not clicked and self.click(_click_match[6], interval=4.5):
                # 有的时候第七个格子被占用到寄养上去了
                # 导致一直无法选上
                clicked = True
                if require_confirmation:
                    confirmation_wait = Timer(10).start()
                continue
            if self.appear_then_click(self.I_U_CIRCLE_ALTERNATE, interval=2.5):
                self.appear_then_click(self.I_U_CONFIRM_ALTERNATE, interval=1.5)
                continue
        logger.info('Set shikigami: %d' % shikigami_order)
        return True

    def detect_no_shikigami(self) -> bool:
        self.screenshot()
        if self.appear(self.I_DETECT_EMPTY_1)\
            or self.appear(self.I_DETECT_EMPTY_2) \
                or self.appear(self.I_DETECT_EMPTY_3) \
                or self.appear(self.I_DETECT_EMPTY_4) \
                or self.appear(self.I_DETECT_EMPTY_5) \
                or self.appear(self.I_DETECT_EMPTY_6):
            return True
        return False
