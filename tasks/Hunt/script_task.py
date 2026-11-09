# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import timedelta, datetime, time
from cached_property import cached_property

from module.exception import TaskEnd, GameStuckError
from module.logger import logger
from module.base.timer import Timer
from module.atom.ocr import RuleOcr

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_hunt, page_hunt_kirin, page_shikigami_records
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.Hunt.assets import HuntAssets
from tasks.GuildQuickParticipation.kirin import open_guild, GUILD_HUNT, GUILD_TASK, COURTYARD_GUILD, HUNT_TITLE
from tasks.GuildQuickParticipation.netherworld import wait_step, open_activity, click


class ScriptTask(GameUi, GeneralBattle, GeneralInvite, SwitchSoul, HuntAssets):
    kirin_day = True  # 不是麒麟就是阴界之门
    tomorrow_kirin_day = True  # 明天是麒麟还是阴界之门

    def run(self):
        self.con_time = self.config.hunt.hunt_time
        if not self.check_datetime():
            # 设置下次运行时间 为今天的晚上七点钟
            raise TaskEnd('Hunt')
        con = self.config.hunt.hunt_config
        if con.kirin_group_team != '-1,-1' or con.netherworld_group_team != '-1,-1':
            self.ui_get_current_page()
            self.ui_goto(page_shikigami_records)

            if self.kirin_day:
                if con.kirin_group_team != '-1,-1':
                    self.run_switch_soul(con.kirin_group_team)
            else:
                if con.netherworld_group_team != '-1,-1':
                    self.run_switch_soul(con.netherworld_group_team)
        self.ui_get_current_page()
        if not self.ui_goto_page(page_main, timeout=35):
            raise GameStuckError('狩猎战无法返回庭院')
        try:
            if self.kirin_day:
                open_guild(self)
                def open_kirin():
                    if not self.appear(GUILD_HUNT):
                        return False
                    x, y, w, h = GUILD_HUNT.roi_front
                    self.device.click(210, y + h // 2 + 30, control_name='hunt_guild_open_kirin')
                    return True
                wait_step(self, '从阴阳寮进入狩猎战', lambda: self.appear(HUNT_TITLE), open_kirin)
            else:
                # Weekend guild sidebar has 阴界之门, not 狩猎战.
                wait_step(self, '进入阴阳寮', lambda: self.appear(GUILD_TASK),
                          lambda: self.appear(COURTYARD_GUILD) and click(self, 580, 644, 'hunt_guild_open'))
                wait_step(self, '从阴阳寮进入阴界之门活动', lambda: self.appear(self.I_NW),
                          lambda: open_activity(self))
        except GameStuckError as error:
            logger.error('寮活动入口未确认，30 分钟后重试：%s', error)
            self.device.save_screenshot(genre='hunt_guild_navigation_failed', interval=0)
            try:
                self.config.notifier.push(title='狩猎战入口未确认', content=str(error))
            except Exception:
                logger.exception('狩猎战入口失败通知未发送')
            self.set_next_run('Hunt', finish=True, server=False, target=datetime.now() + timedelta(minutes=30))
            raise TaskEnd('Hunt')
        if self.kirin_day:
            self.kirin()
        else:
            self.netherworld()
        sleep(1)

        self.plan_tomorrow_hunt()
        raise TaskEnd('Hunt')

    def check_datetime(self) -> bool:
        """
        检查日期和时间, 会设置是麒麟还是阴界之门
        :return: 符合麒麟19:00-21:00、阴界19:00-23:00的时间返回True, 否则返回False
        """
        now = datetime.now()
        day_of_week = now.weekday()
        if 0 <= day_of_week <= 3:
            self.kirin_day = True
        elif 4 <= day_of_week <= 6:
            self.kirin_day = False
        
        if 3 <= day_of_week <= 5:
            self.tomorrow_kirin_day = False
        else:
            self.tomorrow_kirin_day = True

        now = datetime.now()
        # 如果时间在可执行时间(麒麟日6:00、阴界日19:00)之前则设定时间为当天的自定义时间，返回False
        # 如果是在可执行时间则返回True
        if self.kirin_day:
            logger.info('Today is the Kirin day')
            if now.time() < time(6, 0):
                self.custom_next_run(task='Hunt', custom_time=self.con_time.kirin_time, time_delta=0)
                raise TaskEnd('Hunt')
            # 如果是麒麟日在23:00-23:59之间则设定时间为明天的自定义时间，返回False
            elif now.time() > time(23, 0):
                self.plan_tomorrow_hunt()
                raise TaskEnd('Hunt')
            else:
                return True
        else:
            logger.info('Today is the Netherworld day')
            if now.time() < time(17, 0):
                self.custom_next_run(task='Hunt', custom_time=self.con_time.netherworld_time, time_delta=0)
                raise TaskEnd('Hunt')
            # 如果是阴界日在23:00-23:59之间则设定时间为明天的自定义时间，返回False
            elif now.time() > time(23, 0):
                self.plan_tomorrow_hunt()
                raise TaskEnd('Hunt')
            else:
                return True

    def plan_tomorrow_hunt(self):
        # 安排次日狩猎战，便于复用
        if self.tomorrow_kirin_day:
            logger.info('Tomorrow is the Kirin day')
            self.custom_next_run(task='Hunt', custom_time=self.con_time.kirin_time, time_delta=1)
        else:
            logger.info('Tomorrow is the Netherworld day')
            self.custom_next_run(task='Hunt', custom_time=self.con_time.netherworld_time, time_delta=1)

    def kirin(self):
        logger.hr('kirin', 2)
        while 1:
            self.screenshot()
            if self.appear(self.I_PREPARE_HIGHLIGHT):
                break
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.9)\
                    or self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=0.9):
                continue
            if self.appear_then_click(self.I_KIRIN_CHALLAGE, interval=1.5):
                continue
            if self.appear_then_click(self.I_KIRIN_START_CHALLAGE, interval=2.5):
                continue
            if self.appear(self.I_KIRIN_END):
                # 今日已挑战
                logger.warning('Today have already challenged the Kirin')
                self.ui_click_until_disappear(self.I_UI_BACK_YELLOW)
                return
        logger.info('Start battle')
        self.run_general_battle(self.config.hunt.kirin_battle_config)

    def netherworld(self):
        logger.hr('netherworld', 2)
        start_prompt = RuleOcr(roi=(420, 275, 440, 90), area=(420, 275, 440, 90),
                               mode='Full', method='Default', keyword='', name='hunt_nether_start_round')
        last_prompt_click = 0.0
        while 1:
            self.screenshot()
            # The current start-round confirmation is not the generic yellow
            # confirmation template. Require its specific text before clicking.
            words = ''.join(row.ocr_text for row in start_prompt.detect_and_ocr(self.device.image)).replace(' ', '')
            if '是否要从' in words and '轮战斗' in words and '开始' in words:
                from time import monotonic
                if monotonic() - last_prompt_click >= 1.5:
                    self.device.click(750, 438, control_name='hunt_confirm_start_round')
                    last_prompt_click = monotonic()
                sleep(.3)
                continue
            if self.is_in_room(False):
                self.screenshot()
                if not self.appear(self.I_FIRE):
                    continue
                self.click_fire()
                break

            if self.appear_then_click(self.I_NW, interval=0.9):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.9):
                continue
            if self.appear_then_click(self.I_NW_CHALLAGE, interval=1.5):
                continue
            if self.appear(self.I_NW_DONE):
                # 今日已挑战
                logger.warning('Today have already challenged the Netherworld')
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
                return
        logger.info('Start battle')
        self.run_general_battle(self.config.hunt.netherworld_battle_config)

    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        """
        重写，
        阴界之门： 胜利后回到狩猎战的主界面
        麒麟： 胜利后回到麒麟的主界面
        :param random_click_swipt_enable:
        :return:
        """
        # if self.kirin_day:
        #     return super().battle_wait(random_click_swipt_enable)

        # 阴界之门
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        # 战斗过程 随机点击和滑动 防封
        logger.info("Start battle process")
        stuck_timer = Timer(180)
        stuck_timer.start()
        while 1:
            self.screenshot()
            if self.appear(self.I_WIN):
                logger.info('Battle win')
                self.ui_click_until_disappear(self.I_WIN)
                return True
            # 如果出现失败 就点击，返回False
            if self.appear(self.I_FALSE, threshold=0.8):
                logger.info("Battle result is false")
                self.ui_click_until_disappear(self.I_FALSE)
                return False
            if self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=1.5):
                logger.info('Netherworld click prepare after maybe failed')
                self.device.stuck_record_add('BATTLE_STATUS_S')
                continue
            # 如果三分钟还没打完，再延长五分钟
            if stuck_timer and stuck_timer.reached():
                stuck_timer = None
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()

