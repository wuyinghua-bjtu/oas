# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import random
from module.base.timer import Timer
from module.exception import (RequestHumanTakeover, GameTooManyClickError,
                              GameStuckError, GameBlackScreenError, GameSessionExpiredError)
from module.logger import logger
from tasks.Restart.assets import RestartAssets
from tasks.GameUi.assets import GameUiAssets
from tasks.Component.GeneralBuff.assets import GeneralBuffAssets
from tasks.base_task import BaseTask
from tasks.WantedQuests.assets import WantedQuestsAssets
import time

class LoginHandler(BaseTask, RestartAssets, GameUiAssets, GeneralBuffAssets):
    character: str

    def __init__(self, *wargs, **kwargs):
        super().__init__(*wargs, **kwargs)
        self.character = self.config.restart.login_character_config.character
        self.O_LOGIN_SPECIFIC_SERVE.keyword = self.character
        # self.specific_usr = kwargs['config'].

    def _app_handle_login(self) -> bool:
        """
        最终是在庭院界面
        :return:
        """
        logger.hr('App login')
        self.device.stuck_record_add('LOGIN_CHECK')

        confirm_timer = Timer(1.5, count=2).start()
        orientation_timer = Timer(10)
        login_success = False
        black_screen_count = 0
        session_retry_count = 0
        login_idle_rounds = 0

        while 1:
            clicks_before = len(self.device.click_record)
            # Watch device rotation
            if not login_success and orientation_timer.reached():
                # Screen may rotate after starting an app
                self.device.get_orientation()
                orientation_timer.reset()

            try:
                self.screenshot()
            except GameSessionExpiredError:
                # Already confirmed by the common handler. Do not treat the
                # darkened courtyard behind the dialog as a successful login.
                login_success = False
                confirm_timer.reset()
                black_screen_count = 0
                session_retry_count += 1
                wait_seconds = min(5 * session_retry_count, 60)
                logger.warning('Session lost during login; retry login in %ss', wait_seconds)
                time.sleep(wait_seconds)
                continue
            if self.device.last_screenshot_black:
                black_screen_count += 1
                logger.warning('Login capture is pure black (%s/8)', black_screen_count)
                # A freshly restarted client stays black for tens of seconds;
                # only give up after about 40s of continuous black frames.
                if black_screen_count >= 8:
                    raise GameBlackScreenError('Pure-black login capture')
                time.sleep(5)
                continue
            black_screen_count = 0
            # A darkened courtyard remains recognizable behind this modal.
            # Dismiss it before accepting courtyard markers as login success.
            if self.appear_then_click(self.I_LOGIN_LOGIN_CANCEL_BIND_PHONE, interval=1):
                login_success = False
                confirm_timer.reset()
                logger.info('Cancel phone binding form already open at login')
                continue
            if self.appear_then_click(self.I_LOGIN_LOGIN_GOTO_BIND_PHONE, interval=1):
                login_success = False
                confirm_timer.reset()
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    self.screenshot()
                    if self.appear_then_click(self.I_LOGIN_LOGIN_CANCEL_BIND_PHONE, interval=1):
                        logger.info('Close optional phone association prompt')
                        break
                else:
                    raise GameStuckError('Cannot dismiss phone association prompt')
                continue
            # 取消继续战斗
            if self.appear_then_click(self.I_CANCEL_BATTLE, interval=0.8):
                logger.info('Cancel continue battle')
                continue
            # 确认进入庭院(优化：先检测加成图标确认在庭院页面，再检测式神录图标)
            # Page observations must not be interval-throttled: a throttled
            # False is not an absent marker and would reset confirmation on
            # alternate frames even while the courtyard remains visible.
            buff_visible = self.appear(self.I_BUFF_1)
            main_visible = self.appear(self.I_CHECK_MAIN)
            records_visible = self.appear(self.I_MAIN_GOTO_SHIKIGAMI_RECORDS)
            courtyard_visible = (buff_visible
                                 or ((main_visible or records_visible)
                                     and self.appear(WantedQuestsAssets.I_WQ_SEAL)))
            if courtyard_visible:
                # 加成图标存在，确认在庭院页面
                if records_visible or main_visible:
                    # 式神录图标存在，认为已在庭院
                    if not login_success:
                        login_success = True
                        confirm_timer.reset()
                    if confirm_timer.reached():
                        login_success = True
                        logger.info('Login to main confirmed by courtyard markers')
                        break
                    # The courtyard is already visible. Wait for confirmation
                    # without running login-popup actions against its icons.
                    continue
                else:
                    # 式神录图标不存在，点击展开卷轴
                    if self.click(self.C_LOGIN_SCROLL_CLOSE_AREA, interval=2):
                        logger.info('Click scroll expand area because shikigami records not found')
                        self.screenshot()
                        continue
                    confirm_timer.reset()

            if not courtyard_visible:
                login_success = False
                confirm_timer.reset()

            # 网络异常
            # if self.ocr_appear(self.O_LOGIN_NETWORK):
            #     logger.error('Network error')
            #     raise RequestHumanTakeover('Network error')

            # 跳过观看视频
            # if self.ocr_appear_click(self.O_LOGIN_SKIP_1, interval=1):
            #     continue
            # 下载插画
            if self.appear_then_click(self.I_LOGIN_LOAD_DOWN, interval=1):
                logger.info('Download inbetweening')
                continue
            # 不观看视频
            if self.appear_then_click(self.I_WATCH_VIDEO_CANCEL, interval=0.6):
                logger.info('Close video')
                continue
            # 右上角的红色的关闭
            if self.appear_then_click(self.I_LOGIN_RED_CLOSE, interval=0.6):
                logger.info('Close red close')
                continue
            # 左上角的黄色关闭
            if self.appear_then_click(self.I_LOGIN_YELLOW_CLOSE, interval=0.6):
                logger.info('Close yellow close')
                continue
            # 关闭各种邀请弹窗(主要时结界卡寄养邀请)
            from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as gia
            if self.appear_then_click(gia.I_I_REJECT, interval=0.8):
                logger.info("reject invites")
                continue
            # The "精灵" icon is a persistent entrance, not a popup's close
            # button. Never click it while waiting for the courtyard to load.
            # 点击屏幕进入游戏
            if self.appear(self.I_LOGIN_SPECIFIC_SERVE, interval=0.6) \
                    and self.ocr_appear_click(self.O_LOGIN_SPECIFIC_SERVE, interval=0.6):
                while True:
                    self.screenshot()
                    if self.appear(self.I_LOGIN_SPECIFIC_SERVE):
                        self.click(self.C_LOGIN_ENSURE_LOGIN_CHARACTER_IN_SAME_SVR, interval=2)
                        continue
                    break
                logger.info('login specific user')
                continue
            
            # 创建角色, 误入新区直接重启
            if self.appear(self.I_CREATE_ACCOUNT):
                logger.warning('Appear create account')
                raise GameStuckError('Appear create account')

            # 点击“进入游戏”速度过快会进入区服设置，同时需在检测I_LOGIN_8之前检测，因为新服图标会让I_LOGIN_8向右偏移导致永远无法检测成功
            # 同时修复了点击位置（之前是点击I_CHARACTARS而不是左边的区域）
            if self.appear(self.I_CHARACTARS, interval=1):
                logger.info('误入区服设置')
                # https://github.com/runhey/OnmyojiAutoScript/issues/585
                self.device.click(x=106, y=535)
                
            # 登录页的背景/区服装饰会随版本更新；不要用左下角旧的
            # “8”图标作为进入游戏按钮识别的前置条件。该图标变化时，
            # 即使按钮模板或 OCR 能识别到“进入”，旧逻辑也会一直跳过。

            # 登录体验服时，点击“进入游戏”速度过快，可能会出现体验服的弹窗
            if self.appear(self.I_EARLY_SERVER):
                if self.appear_then_click(self.I_EARLY_SERVER_CANCEL):
                    logger.info('Cancel switch from early server to normal server')
                    continue
            # 登录页“进入游戏”按钮优先使用图像模板；
            # OCR仅作兼容旧页面和轻微缩放后的降级识别。
            if (self.appear_then_click(self.I_LOGIN_ENTER_GAME, interval=3)
                    or self.ocr_appear_click(self.O_LOGIN_ENTER_GAME, interval=3)):
                self.wait_until_appear(self.I_LOGIN_SPECIFIC_SERVE, True, wait_time=5)
                continue

            # 网络异常时登录页会停在“服务器/角色列表没加载出来”的状态，
            # 一直空转不出结果。这时交回控制权，让上层重新执行一遍切号动作。
            if len(self.device.click_record) == clicks_before:
                login_idle_rounds += 1
                if login_idle_rounds >= 120:
                    logger.warning('Login page stopped responding for %s rounds; re-run the account switch',
                                   login_idle_rounds)
                    raise GameStuckError('Login page did not load the server list')
            else:
                login_idle_rounds = 0

        return login_success

    def app_handle_login(self) -> bool:
        normal_failure_count = 0
        black_restart_count = 0
        while True:
            self.device.stuck_record_clear()
            self.device.click_record_clear()
            try:
                self._app_handle_login()
                if self.config.restart.harvest_config.enable:
                    self.harvest()
                return True
            except GameSessionExpiredError:
                # Also covers server selection and post-login harvest.
                logger.warning('Session lost during login actions; return to login')
                time.sleep(10)
                continue
            except GameBlackScreenError as e:
                black_restart_count += 1
                wait_seconds = min(10 * black_restart_count, 60)
                logger.warning('%s; restart game and retry login in %ss', e, wait_seconds)
                self.device.app_stop()
                time.sleep(2)
                self.device.app_start()
                time.sleep(wait_seconds)
                continue
            except (GameTooManyClickError, GameStuckError) as e:
                logger.warning(e)
                normal_failure_count += 1
                self.device.app_stop()
                self.device.app_start()
                if normal_failure_count < 2:
                    continue
                break

        logger.critical('Login failed more than 3')
        logger.critical('Onmyoji server may be under maintenance, or you may lost network connection')
        raise RequestHumanTakeover

    def _harvest_main_visible(self):
        """Use independent courtyard markers, never a missing reward as proof."""
        return (self.appear(self.I_BUFF_1)
                and self.appear(self.I_MAIN_GOTO_SHIKIGAMI_RECORDS))

    def _harvest_navigation_failed(self, reason):
        logger.warning(reason)
        self.device.save_screenshot(genre='login_harvest_navigation', interval=0)
        # Leave recovery to app_handle_login's existing bounded failure budget.
        # Do not clear click history or continue harvesting on an unknown page.
        raise GameStuckError(reason)

    def _harvest_close_overlay(self, target):
        """Click a confirmed back button, then wait for an observed transition.

        An interval-throttled `appear` returning False does not mean that the
        button disappeared. All observations here use fresh, unthrottled frames.
        The per-harvest budget also covers briefly disappearing/reappearing UI.
        """
        if not self.appear(target):
            return False
        if self._harvest_main_visible():
            return False
        time.sleep(0.25)
        self.screenshot()
        if not self.appear(target):
            return True  # Transient sample; consume it without clicking.
        if self._harvest_main_visible():
            return False

        for attempt in range(1, 4):
            if self._harvest_close_count >= 6:
                self._harvest_navigation_failed('Harvest back-button budget exhausted')
            self.click(target)
            self._harvest_close_count += 1
            deadline = time.monotonic() + 4
            absent_frames = 0
            while time.monotonic() < deadline:
                time.sleep(0.35)
                self.screenshot()
                if self.appear(target):
                    absent_frames = 0
                else:
                    absent_frames += 1
                    if absent_frames >= 2:
                        logger.info('Harvest back transition confirmed: %s', target.name)
                        return True
            logger.warning('Harvest back button unchanged after attempt %s/3: %s',
                           attempt, target.name)
        self._harvest_navigation_failed('Harvest back navigation did not change the page')

    def harvest(self):
        """
        获得奖励
        :return: 如果没有发现任何奖励后退出
        """
        logger.hr('Harvest')
        timer_harvest = Timer(5)  # 如果连续5秒没有发现任何奖励，退出
        harvest_deadline = time.monotonic() + 120
        self._harvest_close_count = 0
        skip_default = False
        courtyard_affairs_done = False  # 庭院事务只执行一次
        while 1:
            self.screenshot()
            if time.monotonic() >= harvest_deadline:
                self._harvest_navigation_failed('Harvest did not return to courtyard within 120s')

            # 点击'获得奖励'
            if self.ui_reward_appear_click():
                timer_harvest.reset()
                continue
            # 获得奖励
            if self.appear_then_click(self.I_UI_AWARD, interval=0.2):
                timer_harvest.reset()
                continue
            # 偶尔会打开到聊天频道
            if self.appear_then_click(self.I_HARVEST_CHAT_CLOSE, interval=1):
                timer_harvest.reset()
                continue
            # 偶尔会进入其他页面
            # 左上角的黄色关闭
            if self._harvest_close_overlay(self.I_LOGIN_YELLOW_CLOSE):
                timer_harvest.reset()
                logger.info('Close yellow close')
                continue
            # 关闭宠物小屋
            if self._harvest_close_overlay(self.I_HARVEST_BACK_PET_HOUSE):
                timer_harvest.reset()
                logger.info('Close yellow close')
                continue
            # 御魂溢确认
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=2.5):
                timer_harvest.reset()
                skip_default = True
                logger.info('Soul overflow')
                continue
            # 关闭姿度出现的蒙版
            if self.appear(self.I_HARVEST_ZIDU, interval=1):
                timer_harvest.reset()
                self.I_HARVEST_ZIDU.roi_front[0] -= 200
                self.I_HARVEST_ZIDU.roi_front[1] -= 200
                if self.click(self.I_HARVEST_ZIDU, interval=2):
                    logger.info('Close zidu')
                continue

            # 庭院事务
            if self.config.restart.harvest_config.enable_courtyard_affairs and not courtyard_affairs_done:
                self.harvest_courtyard_affairs()
                timer_harvest.reset()
                courtyard_affairs_done = True
                continue
            # 勾玉
            if self.appear_then_click(self.I_HARVEST_JADE, interval=1.5):
                timer_harvest.reset()
                continue
            # 签到
            if self.appear_then_click(self.I_HARVEST_SIGN, interval=1.5):
                self.wait_until_appear(self.I_HARVEST_SIGN_2, wait_time=2)
                timer_harvest.reset()
                continue
            # 某些活动的特殊签到，有空看到就删掉
            if self.appear_then_click(self.I_HARVEST_SIGN_3, interval=0.7):
                timer_harvest.reset()
                continue
            if self.appear_then_click(self.I_HARVEST_SIGN_4, interval=1):
                timer_harvest.reset()
                continue
            if self.appear_then_click(self.I_HARVEST_SIGN_2, interval=1.5):
                self.wait_until_appear(self.I_LOGIN_RED_CLOSE, wait_time=2)
                timer_harvest.reset()
                continue
            # 999天的签到福袋
            if self.appear_then_click(self.I_HARVEST_SIGN_999, interval=1.5):
                timer_harvest.reset()
                continue
            # 判断是否勾选了收取邮件（不收取邮件可以查看每日收获）
            if not skip_default and self.config.restart.harvest_config.enable_mail and self.harvest_mail():
                timer_harvest.reset()
                continue
            if self.appear_then_click(self.I_HARVEST_AP, interval=1, threshold=0.7):
                timer_harvest.reset()
                continue
            # 御魂觉醒加成
            if self.appear_then_click(self.I_HARVEST_SOUL, interval=1):
                timer_harvest.reset()
                continue
            # 寮包
            if self.appear_then_click(self.I_HARVEST_GUILD_REWARD, interval=2):
                timer_harvest.reset()
                continue
            # 自选御魂
            if not skip_default and self.appear(self.I_HARVEST_SOUL_1):
                logger.info('Select soul 2')
                self.ui_click(self.I_HARVEST_SOUL_1, stop=self.I_HARVEST_SOUL_2)
                self.ui_click(self.I_HARVEST_SOUL_2, stop=self.I_HARVEST_SOUL_3, interval=3)
                self.ui_click_until_disappear(click=self.I_HARVEST_SOUL_3)
                timer_harvest.reset()

            # 红色的关闭
            if self.appear(self.I_LOGIN_RED_CLOSE):
                self.click(self.I_LOGIN_RED_CLOSE, interval=2)
                timer_harvest.reset()
                continue

            # 五秒内没有发现任何奖励，退出
            if not timer_harvest.started():
                timer_harvest.start()
            else:
                if timer_harvest.reached():
                    if self._harvest_main_visible():
                        time.sleep(0.35)
                        self.screenshot()
                        if self._harvest_main_visible():
                            logger.info('No more reward; courtyard confirmed on two frames')
                            return

    def set_specific_usr(self, character: str):
        self.character = character
        self.O_LOGIN_SPECIFIC_SERVE.keyword = character

    def harvest_mail(self) -> bool:
        if not self.appear_multi_scale(self.I_HARVEST_MAIL,scale_range=(0.8, 1.1)) and \
                not self.appear(self.I_HARVEST_MAIL_COPY):
            if not self.appear(self.I_READ_ALL_MAIL):
                return False
        logger.info('Harvest mail')
        while 1:
            self.screenshot()
            if self.appear(self.I_READ_ALL_MAIL):
                break
            if self.appear_then_click_multi_scale(self.I_HARVEST_MAIL, interval=1.5, scale_range=(0.8, 1.1)):
                continue
            if self.appear_then_click(self.I_HARVEST_MAIL_COPY, interval=1.5):
                continue
        timeout_timer = Timer(3).start()
        logger.info('Exec harvest mail')
        while 1:
            self.screenshot()
            if timeout_timer.reached():
                break
            if self.appear_then_click(self.I_HARVEST_MAIL_CONFIRM, interval=0.8):
                break

            if self.appear_then_click(self.I_READ_ALL_MAIL, interval=1.5):
                continue
            if self.appear_then_click(self.I_HARVEST_MAIL_ALL, interval=1.5):
                continue
            if self.appear_then_click(self.I_MAIL_RED_POINT, interval=4):
                continue
        self.ui_click_until_disappear(self.I_LOGIN_RED_CLOSE)
        return True
    
    def harvest_courtyard_affairs(self) -> bool:
        if not self.ui_click_multi_scale(self.I_NOTE, self.I_PAGE, timeout=3, scale_range=(0.8, 1.2)):
            logger.warning('courtyard affairs timeout!')
            return False
        count_success = 0
        while 1:
            self.screenshot()
            if self.appear(self.I_NO_TASKS):
                logger.info('courtyard affairs completed！')
                break
            # 每日六星御魂
            if self.appear_then_click(self.I_HARVEST_SOUL_2, interval=1) \
                    or self.appear_then_click(self.I_HARVEST_SOUL_3, interval=1):
                continue
            # 点击'获得奖励'
            if self.ui_reward_appear_click():
                continue
            # 获得奖励
            if self.appear_then_click(self.I_UI_AWARD, interval=0.2):
                continue
            # 式神满级，是否提取物经验？确定
            if self.appear_then_click(self.I_CONFIRM, interval=1):
                continue

            if self.appear_then_click(self.I_DAILY, interval=1):
                continue
            # 领取成功： 太傻逼了收取结界奖励游戏里面居然没有加上限制
            if self.appear_then_click(self.I_SUCCESS_CLAIMED, interval=1):
                continue
            if self.appear_then_click(self.I_SKIP):# 万花牌跳过
                continue
            if self.appear_then_click(self.I_LOGIN_RED_CLOSE, interval=1):# 万花牌X
                continue
            # 一键完成
            if count_success >= 3:
                logger.info(f'Click complete tasks {count_success} times')
                break
            if self.appear_then_click(self.I_COMPLETE_TASKS, interval=2.3):
                count_success += 1
                continue
        return True
