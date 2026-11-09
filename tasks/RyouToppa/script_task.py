# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import time
from datetime import datetime, timedelta
from pathlib import Path
import random

from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.RyouToppa.assets import RyouToppaAssets
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.config_base import ConfigBase, Time
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_realm_raid, page_main, page_kekkai_toppa, page_shikigami_records
from tasks.RealmRaid.assets import RealmRaidAssets

from module.logger import logger
from module.exception import TaskEnd
from module.atom.image_grid import ImageGrid
from module.base.utils import point2str
from module.base.timer import Timer
from module.exception import GamePageUnknownError



area_map = (
    {
        "fail_sign": (RyouToppaAssets.I_AREA_1_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_1_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_1,
        "finished_sign": (RyouToppaAssets.I_AREA_1_FINISHED, RyouToppaAssets.I_AREA_1_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_2_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_2_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_2,
        "finished_sign": (RyouToppaAssets.I_AREA_2_FINISHED, RyouToppaAssets.I_AREA_2_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_3_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_3_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_3,
        "finished_sign": (RyouToppaAssets.I_AREA_3_FINISHED, RyouToppaAssets.I_AREA_3_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_4_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_4_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_4,
        "finished_sign": (RyouToppaAssets.I_AREA_4_FINISHED, RyouToppaAssets.I_AREA_4_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_5_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_5_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_5,
        "finished_sign": (RyouToppaAssets.I_AREA_5_FINISHED, RyouToppaAssets.I_AREA_5_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_6_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_6_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_6,
        "finished_sign": (RyouToppaAssets.I_AREA_6_FINISHED, RyouToppaAssets.I_AREA_6_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_7_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_7_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_7,
        "finished_sign": (RyouToppaAssets.I_AREA_7_FINISHED, RyouToppaAssets.I_AREA_7_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_8_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_8_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_8,
        "finished_sign": (RyouToppaAssets.I_AREA_8_FINISHED, RyouToppaAssets.I_AREA_8_FINISHED_NEW)
    }
)


def random_delay(min_value: float = 1.0, max_value: float = 2.0, decimal: int = 1):
    """
    生成一个指定范围内的随机小数
    """
    random_float_in_range = random.uniform(min_value, max_value)
    return (round(random_float_in_range, decimal))

class ScriptTask(GeneralBattle, GameUi, SwitchSoul, RyouToppaAssets):
    medal_grid: ImageGrid = None

    def battle_settlement_requires_confirmation(self) -> bool:
        return True

    def battle_settlement_return_visible(self) -> bool:
        # A battle result may temporarily lose its reward image. Only the raid
        # board's record control plus an independent board marker proves exit.
        return self.appear(self.I_TOPPA_RECORD) and any(self.appear(asset) for asset in (
            self.I_KEKKAI_TOPPA, self.I_RYOU_REWARD, self.I_RYOU_REWARD_90,
            self.I_SUCCESS_PENETRATION))

    PATROL_INTERVAL = timedelta(minutes=10)
    MANUAL_RUN_MARKER = Path(__file__).resolve().parents[2] / 'config' / '.ryou_toppa_manual_once'

    @classmethod
    def _consume_manual_run(cls) -> int | None:
        """Consume a one-shot manual run request and return its attack interval."""
        try:
            raw = cls.MANUAL_RUN_MARKER.read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            return None
        try:
            interval = max(0, int(raw))
        except ValueError:
            interval = 10
        cls.MANUAL_RUN_MARKER.unlink(missing_ok=True)
        return interval

    @classmethod
    def _next_patrol_time(cls, now: datetime) -> datetime:
        """Return the next patrol time, including during nighttime."""
        return now.replace(microsecond=0) + cls.PATROL_INTERVAL

    def schedule_next_patrol(self, success: bool) -> None:
        target = self._next_patrol_time(datetime.now())
        logger.info('RyouToppa patrol result=%s; next patrol=%s', success, target)
        self.set_next_run(task='RyouToppa', finish=True, server=False, target=target)

    def schedule_completed_day(self):
        now = datetime.now()
        target = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        logger.info('RyouToppa cleared; skip remaining patrols today, next check=%s', target)
        self.set_next_run(task='RyouToppa', finish=True, server=False, target=target)

    def prepare_attack_souls(self):
        if self._souls_prepared:
            return
        conf = self.config.ryou_toppa.switch_soul_config
        if conf.enable or conf.enable_switch_by_name:
            self.ui_get_current_page()
            self.ui_goto(page_shikigami_records)
            if conf.enable:
                self.run_switch_soul(conf.switch_group_team)
            if conf.enable_switch_by_name:
                self.run_switch_soul_by_name(conf.group_name, conf.team_name)
            self.ui_get_current_page()
            if not self.ui_goto(page_kekkai_toppa):
                logger.error('无法返回寮突破页面，延后巡查')
                self.schedule_next_patrol(success=False)
                raise TaskEnd('RyouToppa')
        self._souls_prepared = True

    def run(self):
        """
        执行
        :return:
        """
        ryou_config = self.config.ryou_toppa
        now = datetime.now()
        self._manual_attack_interval = self._consume_manual_run()
        manual_run = self._manual_attack_interval is not None
        if manual_run:
            logger.info('Consume manual RyouToppa request; attack interval=%ss',
                        self._manual_attack_interval)
        time_limit: Time = ryou_config.raid_config.limit_time
        time_delta = timedelta(hours=time_limit.hour, minutes=time_limit.minute, seconds=time_limit.second)
        self.medal_grid = ImageGrid([RealmRaidAssets.I_MEDAL_5, RealmRaidAssets.I_MEDAL_4, RealmRaidAssets.I_MEDAL_3,
                                     RealmRaidAssets.I_MEDAL_2, RealmRaidAssets.I_MEDAL_1, RealmRaidAssets.I_MEDAL_0])

        self._souls_prepared = False

        self.ui_get_current_page()
        if not self.ui_goto(page_kekkai_toppa):
            logger.error('无法进入寮突破页面，延后巡查以便其他任务继续')
            self.schedule_next_patrol(success=False)
            raise TaskEnd('RyouToppa')
        ryou_toppa_start_flag = True
        ryou_toppa_success_penetration = False
        ryou_toppa_admin_flag = False
        # 点击突破
        while 1:
            self.screenshot()
            if self.appear_then_click(RealmRaidAssets.I_REALM_RAID, interval=1):
                continue
            if self.appear(self.I_REAL_RAID_REFRESH, threshold=0.8):
                if self.appear_then_click(self.I_RYOU_TOPPA, interval=1):
                    continue
            # 攻破阴阳寮，说明寮突已开，则退出
            elif self.appear(self.I_SUCCESS_PENETRATION, threshold=0.8):
                ryou_toppa_start_flag = True
                ryou_toppa_success_penetration = True
                break
            # 出现选择寮突说明寮突未开
            elif self.appear(self.I_SELECT_RYOU_BUTTON, threshold=0.8):
                ryou_toppa_start_flag = False
                ryou_toppa_admin_flag = True
                break
            # 出现晴明说明寮突未开
            elif self.appear(self.I_NO_SELECT_RYOU, threshold=0.8):
                ryou_toppa_start_flag = False
                break
            # 出现寮奖励， 说明寮突已开
            elif self.appear(self.I_RYOU_REWARD, threshold=0.8) or self.appear(self.I_RYOU_REWARD_90, threshold=0.8):
                ryou_toppa_start_flag = True
                break

        logger.attr('ryou_toppa_start_flag', ryou_toppa_start_flag)
        logger.attr('ryou_toppa_success_penetration', ryou_toppa_success_penetration)
        # 寮突未开 并且有权限， 开开寮突，没有权限则标记失败
        if not ryou_toppa_start_flag:
            if ryou_config.raid_config.ryou_access and ryou_toppa_admin_flag:
                # 作为寮管理，开启今天的寮突
                logger.info("As the manager of the ryou, try to start ryou toppa.")
                self.start_ryou_toppa()
            else:
                logger.info("The ryou toppa is not open and you are a ryou member.")
                self.schedule_next_patrol(success=False)
                raise TaskEnd

        # 100% 攻破, 第二天再执行
        if ryou_toppa_success_penetration:
            logger.info('RyouToppa is 100%')
            self.schedule_completed_day()
            raise TaskEnd
        if self.config.ryou_toppa.general_battle_config.lock_team_enable:
            logger.info("Lock team.")
            self.ui_click(self.I_TOPPA_UNLOCK_TEAM, self.I_TOPPA_LOCK_TEAM)
        else:
            logger.info("Unlock team.")
            self.ui_click(self.I_TOPPA_LOCK_TEAM, self.I_TOPPA_UNLOCK_TEAM)
        # --------------------------------------------------------------------------------------------------------------
        # 开始突破
        # --------------------------------------------------------------------------------------------------------------
        area_index = 0
        completed_areas = 0
        success = True
        # Every invocation consumes all currently available chances. When no
        # chance remains, the scheduler returns in ten minutes to check again.
        self._run_attack_limit = None
        while 1:
            self.screenshot()
            if self.appear(self.I_SUCCESS_PENETRATION, threshold=0.8):
                logger.info('RyouToppa is 100%')
                self.schedule_completed_day()
                raise TaskEnd
            if not self.appear(self.I_TOPPA_RECORD, threshold=0.6):
                continue
            # 设置长任务标志,用来寻找寮突可进攻的目标
            self.device.stuck_record_add('PREPARE_BEFORE_BATTLE')
            if not self.has_ticket():
                logger.info("We have no chance to attack. Patrol again after 10 minutes.")
                success = False
                break
            if self.current_count >= self._run_attack_limit:
                logger.warning("We have attacked the limit count.")
                break
            if datetime.now() >= self.start_time + time_delta:
                logger.warning("We have attacked the limit time.")
                break
            # 进攻
            count_before = self.current_count
            res = self.attack_area(area_index)
            if manual_run and self.current_count > count_before and self._manual_attack_interval:
                logger.info('Manual RyouToppa attack interval: %ss', self._manual_attack_interval)
                time.sleep(self._manual_attack_interval)
            # 如果战斗失败或区域不可用，则弹出当前区域索引，开始进攻下一个
            if not res:
                if self._last_area_completed:
                    completed_areas += 1
                area_index += 1
                if area_index >= len(area_map):
                    if completed_areas == len(area_map):
                        logger.info('All RyouToppa areas are completed; treat as 100%')
                        self.schedule_completed_day()
                        raise TaskEnd
                    logger.warning('All areas are not available, it will flush the area cache')
                    area_index = 0
                    completed_areas = 0
                    self.flush_area_cache()
                continue

            # An attack changes the board, so the next full scan starts fresh.
            completed_areas = 0


        # 回 page_main 失败
        # self.ui_current = page_ryou_toppa
        # self.ui_goto(page_main)
        if success:
            self.schedule_next_patrol(success=True)
        else:
            self.schedule_next_patrol(success=False)
        raise TaskEnd

    def start_ryou_toppa(self):
        """
        开启寮突破
        :return:
        """
        # 点击寮突
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_SELECT_RYOU_BUTTON, interval=1):
                break
        logger.info(f'Click {self.I_SELECT_RYOU_BUTTON.name}')

        # 选择第一个寮
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_GUILD_ORDERS_REWARDS, action=self.C_SELECT_FIRST_RYOU, interval=1):
                break
        logger.info(f'Click {self.C_SELECT_FIRST_RYOU.name}')

        # 点击开始突入
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_START_TOPPA_BUTTON, interval=1):
                continue
            # 出现寮奖励， 说明寮突已开
            if self.appear(self.I_RYOU_REWARD, threshold=0.8):
                break
        logger.info(f'Click {self.I_START_TOPPA_BUTTON.name}')

    def has_ticket(self) -> bool:
        """
        如果没有票了，那么就返回False
        :return:
        """
        # 21点后、次日5点前无限进攻机会
        if datetime.now().hour >= 21 or datetime.now().hour <= 5:
            if self._run_attack_limit is None:
                self._run_attack_limit = self.config.ryou_toppa.raid_config.limit_count
            return True
        self.wait_until_appear(self.I_TOPPA_RECORD)
        self.screenshot()
        cu, res, total = self.O_NUMBER.ocr(self.device.image)
        if cu == 0 and cu + res == total:
            logger.warning(f'Execute round failed, no ticket')
            return False
        if self._run_attack_limit is None:
            configured_limit = self.config.ryou_toppa.raid_config.limit_count
            # Consume every currently available chance in this invocation,
            # while retaining limit_count as a safety ceiling.
            self._run_attack_limit = min(configured_limit, self.current_count + cu)
            logger.info(f'RyouToppa invocation attack limit: {self._run_attack_limit} '
                        f'(remaining={cu}/{total})')
        return True

    def check_area(self, index: int) -> bool:
        """
        检查该区域是否攻略失败
        :return:
        """
        self._last_area_completed = False
        f1, f2 = area_map[index].get("fail_sign")
        f3, f4 = area_map[index].get("finished_sign")
        self.screenshot()
        # A completed area is not the same as 100% guild penetration. Skip it
        # and continue scanning the remaining areas.
        if self.appear(f3, threshold=0.8) or self.appear(f4, threshold=0.8):
            logger.info('Area [%s] is completed, skip.' % str(index + 1))
            self._last_area_completed = True
            return False
        # 如果该区域攻略失败返回 False
        if self.appear(f1, threshold=0.8) or self.appear(f2, threshold=0.8):
            logger.info('Area [%s] is futile attack, skip.' % str(index + 1))
            return False
        return True

    def flush_area_cache(self):
        time.sleep(2)
        duration = 0.352
        count = random.randint(1, 3)
        for i in range(count):
            # 测试过很多次 win32api, win32gui 的 MOUSEEVENTF_WHEEL, WM_MOUSEWHEEL
            # 都出现过很多次离奇的事件，索性放弃了使用以下方法，参数是精心调试的
            # 每次执行刚好刷新一组（2个）设定随机刷新 1 - 3 次
            safe_pos_x = random.randint(540, 1000)
            safe_pos_y = random.randint(320, 540)
            p1 = (safe_pos_x, safe_pos_y)
            p2 = (safe_pos_x, safe_pos_y - 101)
            logger.info('Swipe %s -> %s, %s ' % (point2str(*p1), point2str(*p2), duration))
            self.device.swipe(p1, p2, duration=duration,
                              control_name='RyouToppaRefreshArea')
            time.sleep(2)

    def attack_area(self, index: int):
        """
        :return: 战斗成功(True) or 战斗失败(False) or 区域不可用（False） or 没有进攻机会（设定下次运行并退出）
        """
        # 每次进攻前检查区域可用性
        if not self.check_area(index):
            return False

        # Cleared regions never trigger a trip to the soul preset screen.
        self.prepare_attack_souls()
        if not self.check_area(index):
            return False

        # 正式进攻会设定 2s - 10s 的随机延迟，避免攻击间隔及其相近被检测为脚本。
        if self.config.ryou_toppa.raid_config.random_delay:
            delay = random_delay()
            time.sleep(delay)


        rcl = area_map[index].get("rule_click")
        # # 点击攻击区域，等待攻击按钮出现。
        # self.ui_click(rcl, stop=RealmRaidAssets.I_FIRE, interval=2)
        # 塔塔开！
        click_failure_count = 0
        while True:
            self.screenshot()
            if click_failure_count >= 5:
                logger.warning("Click failure, check your click position")
                return False
            if not self.appear(self.I_TOPPA_RECORD, threshold=0.85):
                time.sleep(1)
                self.screenshot()
                if self.appear(self.I_TOPPA_RECORD, threshold=0.85):
                    continue
                logger.info("Start attach area [%s]" % str(index + 1))
                return self.run_general_battle(config=self.config.ryou_toppa.general_battle_config)

            if self.appear_then_click(RealmRaidAssets.I_FIRE, interval=2, threshold=0.8):
                click_failure_count += 1
                continue
            if self.click(rcl, interval=5):
                click_failure_count += 1
                continue


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    config = Config('oas1')
    device = Device(config)
    t = ScriptTask(config, device)
    t.run()
