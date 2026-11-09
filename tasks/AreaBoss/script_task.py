# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import time

import cv2
import numpy as np
import random
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from module.atom.click import RuleClick
from tasks.base_task import BaseTask
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_area_boss, page_shikigami_records, page_login, page_exploration
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.AreaBoss.assets import AreaBossAssets
from tasks.AreaBoss.config_boss import AreaBossFloor
from module.logger import logger
from module.exception import TaskEnd, GameStuckError
from module.atom.image import RuleImage
from module.atom.swipe import RuleSwipe
from module.base.timer import Timer
from typing import List


class AreaBossDefeated(GameStuckError):
    """The game explicitly reported a battle defeat."""


class ScriptTask(GeneralBattle, GameUi, SwitchSoul, AreaBossAssets):
    # Keep both ends of the gesture inside the scrollable list.  The older
    # diagonal gestures can begin outside the list and fail to move it.
    S_BOUNTY_TO_TOP = RuleSwipe(roi_front=(1000,270,1,1), roi_back=(1000,640,1,1), mode='default', name='bounty_to_top')
    S_BOUNTY_TO_BOTTOM = RuleSwipe(roi_front=(1000,640,1,1), roi_back=(1000,270,1,1), mode='default', name='bounty_to_bottom')

    def battle_wait(self, random_click_swipt_enable):
        # Ten-star battles can run far longer than ordinary encounters.
        old_timer = self.device.stuck_timer_long
        self.device.stuck_timer_long = Timer(1200, count=300).start()
        try:
            return super().battle_wait(random_click_swipt_enable)
        finally:
            self.device.stuck_timer_long = old_timer

    def run_daily_two_bosses(self):
        """One maximum-popularity bounty and one specifically identified favorite."""
        stage = '准备地域鬼王'
        marker = Path('config') / f'.area_boss_{self.config.config_name}_daily_progress'
        try:
            progress = marker.read_text(encoding='utf-8').strip() if marker.exists() else ''
            if progress == f'{datetime.now().date()}:first_battle':
                self.screenshot()
                if not (self.is_in_real_battle(False) or self.battle_result_visible()):
                    raise GameStuckError('已有未确认的悬赏鬼王战斗，请先确认结果')
                logger.info('恢复等待当前悬赏鬼王战斗，不重复发起挑战')
                stage = '等待已开始的悬赏鬼王战斗'
                if not self.battle_wait(False):
                    marker.unlink(missing_ok=True)
                    raise AreaBossDefeated('已开始的悬赏鬼王战斗失败')
                if not self.wait_until_appear(self.I_AB_CLOSE_RED, wait_time=25):
                    raise GameStuckError('战斗后没有返回鬼王详情')
                self.ui_click_until_disappear(self.I_AB_CLOSE_RED, interval=1)
                marker.write_text(f'{datetime.now().date()}:first_complete', encoding='utf-8')
                progress = f'{datetime.now().date()}:first_complete'
            if progress == f'{datetime.now().date()}:first_complete':
                stage = '查找收藏中的鲤鱼精'
                self.open_favorite_species(self.config.area_boss.boss.favorite_species)
                stage = '挑战收藏中的鲤鱼精'
                self.fight_open_detail_preserving_debuffs()
                marker.unlink(missing_ok=True)
                logger.info('Daily area boss: both requested battles succeeded')
                self.go_back()
                return
            # A manually triggered run can start while the game is still at
            # login. Recover the session before attempting page navigation.
            if self.ui_get_current_page() == page_login:
                logger.warning('地域鬼王启动时处于登录界面，先恢复登录')
                from tasks.Restart.login import LoginHandler
                LoginHandler(config=self.config, device=self.device).app_handle_login()
            soul = self.config.area_boss.switch_soul
            if soul.enable or soul.enable_switch_by_name:
                self.ui_get_current_page()
                if not self.ui_goto(page_shikigami_records):
                    raise GameStuckError('无法进入式神录切换御魂')
                if soul.enable:
                    self.run_switch_soul(soul.switch_group_team)
                if soul.enable_switch_by_name:
                    self.run_switch_soul_by_name(soul.group_name, soul.team_name)
            self.ui_get_current_page()
            if not self.enter_area_boss():
                raise GameStuckError('无法进入地域鬼王')

            stage = '查找人数最多的悬赏鬼王'
            self.open_maximum_bounty()
            stage = '挑战人数最多的悬赏鬼王'
            marker.write_text(f'{datetime.now().date()}:first_battle', encoding='utf-8')
            try:
                self.fight_open_detail_preserving_debuffs()
            except AreaBossDefeated:
                # A confirmed defeat is safe to retry; an interrupted or
                # unrecognized fight must keep its pending marker.
                marker.unlink(missing_ok=True)
                raise
            marker.write_text(f'{datetime.now().date()}:first_complete', encoding='utf-8')

            stage = '查找收藏中的鲤鱼精'
            self.open_favorite_species(self.config.area_boss.boss.favorite_species)
            stage = '挑战收藏中的鲤鱼精'
            self.fight_open_detail_preserving_debuffs()
            marker.unlink(missing_ok=True)
            logger.info('Daily area boss: both requested battles succeeded')
            self.go_back()
        except Exception as error:
            logger.exception(f'地域鬼王失败：{stage}: {error}')
            self.notify_daily_failure(stage, error)
        finally:
            now = datetime.now()
            target = now.replace(hour=15, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            self.set_next_run(task='AreaBoss', finish=True, server=False, target=target)
        raise TaskEnd('AreaBoss')

    def enter_area_boss(self):
        """Retry the known entrance while the exploration page is visible."""
        if not self.ui_goto(page_exploration):
            return False
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            self.screenshot()
            if self.ui_page_appear(page_area_boss):
                self.ui_current = page_area_boss
                return True
            if self.ui_page_appear(page_exploration):
                self.appear_then_click(self.I_EXPLORATION_GOTO_AREA_BOSS, interval=2)
            time.sleep(0.3)
        logger.warning('地域鬼王入口重试后仍未确认进入')
        return False

    def notify_daily_failure(self, stage, error):
        """Send only this task's failures to the configured WeChat channel."""
        try:
            from module.notify.notify import Notifier
            settings = self.config.model.script.error
            notify_config = settings.notify_config if settings.notify_enable else ''
            if not notify_config:
                other = json.loads(Path('config/oas_leveling.json').read_text(encoding='utf-8-sig'))
                push = other.get('script', {}).get('error', {})
                notify_config = push.get('notify_config', '') if push.get('notify_enable') else ''
            if not notify_config:
                logger.error('AreaBoss failure push unavailable: notification channel not configured')
                return False
            notifier = Notifier(notify_config, True)
            notifier.config_name = self.config.config_name.upper()
            ok = notifier.push(title='地域鬼王执行失败', content=f'步骤：{stage}\n原因：{type(error).__name__}: {error}')
            if not ok:
                logger.error('AreaBoss failure notification was not accepted')
            return ok
        except Exception as notify_error:
            logger.error(f'地域鬼王失败推送出错: {type(notify_error).__name__}')
            return False

    def _reward_position(self, index):
        positions = [self.C_AB_BOSS_REWARD_PHOTO_1, self.C_AB_BOSS_REWARD_PHOTO_2,
                     self.C_AB_BOSS_REWARD_PHOTO_3, self.C_AB_BOSS_REWARD_PHOTO_MINUS_2,
                     self.C_AB_BOSS_REWARD_PHOTO_MINUS_1]
        return positions[index]

    def _position_reward_list(self, bottom):
        self.open_filter()
        self.switch_to_reward()
        # A full swipe reaches either endpoint on the five-entry bounty list.
        direction = self.S_BOUNTY_TO_BOTTOM if bottom else self.S_BOUNTY_TO_TOP
        for _ in range(2):
            self.swipe(direction)
            time.sleep(0.5)

    def _read_detail_name(self):
        names = []
        for _ in range(2):
            self.screenshot()
            results = self.O_AB_BOSS_NAME.detect_and_ocr(self.device.image)
            names.append(''.join(result.ocr_text for result in results).strip())
        if not names[0] or names[0] != names[1]:
            raise GameStuckError('鬼王地区名称识别不稳定')
        return names[0]

    def _read_detail_challenge_count(self):
        readings = []
        for _ in range(3):
            self.screenshot()
            raw = self.O_AB_NUM_OF_CHALLENGE.ocr_single(self.device.image)
            digits = re.sub(r'[^0-9]', '', str(raw or ''))
            if digits:
                value = int(digits)
                readings.append(value)
                if readings.count(value) >= 2:
                    return value
        raise GameStuckError('鬼王挑战人数识别不稳定')

    def open_maximum_bounty(self):
        # Positions at opposite scroll endpoints overlap. Identify entries by
        # the detail name, never by an assumed list index after scrolling.
        groups = (
            (False, (self.C_AB_BOSS_REWARD_PHOTO_1, self.C_AB_BOSS_REWARD_PHOTO_2,
                     self.C_AB_BOSS_REWARD_PHOTO_3)),
            (True, (self.C_AB_BOSS_REWARD_PHOTO_MINUS_3, self.C_AB_BOSS_REWARD_PHOTO_MINUS_2,
                    self.C_AB_BOSS_REWARD_PHOTO_MINUS_1)),
        )
        candidates = {}
        for bottom, positions in groups:
            self._position_reward_list(bottom=bottom)
            for position in positions:
                self.open_filter()
                if not self.open_boss_detail(position, 3):
                    logger.warning('悬赏位置 %s 无法打开，无法读取该位置的人数', position.name)
                    continue
                name = self._read_detail_name()
                count = self._read_detail_challenge_count()
                candidates[name] = max(candidates.get(name, 0), count)
                logger.info('已读取悬赏鬼王 %s，挑战人数 %s', name, count)
                self.ui_click_until_disappear(self.I_AB_CLOSE_RED, interval=1)
        if not candidates:
            raise GameStuckError('没有可打开的悬赏鬼王')
        expected, count = max(candidates.items(), key=lambda item: item[1])
        for bottom, positions in groups:
            self._position_reward_list(bottom=bottom)
            for position in positions:
                self.open_filter()
                if not self.open_boss_detail(position, 3):
                    continue
                name = self._read_detail_name()
                if name == expected:
                    logger.info('已确认已读取悬赏中人数最多的目标：%s，%s 人', expected, count)
                    return
                logger.warning('重新定位悬赏时遇到 %s，继续查找 %s', name, expected)
                self.ui_click_until_disappear(self.I_AB_CLOSE_RED, interval=1)
        raise GameStuckError(f'无法重新找到已读取人数最多的悬赏鬼王：{expected}')

    def open_favorite_species(self, expected):
        if not expected:
            raise GameStuckError('未设置收藏鬼王名称')
        self.open_filter()
        self.switch_to_collect()
        for position in (self.C_AB_BOSS_PHOTO_1, self.C_AB_BOSS_PHOTO_2):
            self.open_filter()
            if not self.open_boss_detail(position, 3):
                raise GameStuckError('无法打开收藏鬼王详情')
            names = []
            for _ in range(2):
                self.screenshot()
                names.append(''.join((self.O_AB_BOSS_SPECIES.ocr_single(self.device.image) or '').split()))
            if names == [expected, expected]:
                logger.info(f'已确认收藏鬼王：{expected}')
                return
            self.ui_click_until_disappear(self.I_AB_CLOSE_RED, interval=1)
        raise GameStuckError(f'两个收藏中未能确认 {expected}')

    def _debuff_mask(self):
        template = self.I_AB_DEBUFF_CHECK.image
        result = []
        for y in (237, 318):
            for x in (188, 268, 348, 428, 508, 588):
                region = self.device.image[y-20:y+20, x-20:x+20]
                score = cv2.minMaxLoc(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED))[1]
                result.append(score >= 0.85)
        return tuple(result)

    def ensure_ten_stars_preserving_debuffs(self):
        self.screenshot()
        if not self.get_difficulty():
            if not self.appear(self.I_AB_DIFFICULTY_NORMAL):
                raise GameStuckError('无法确认地域鬼王难度')
            self.switch_difficulty(True)
        self.screenshot()
        if not self.appear(self.I_AB_DIFFICULTY_JI):
            raise GameStuckError('未能确认极难度')
        before = self._debuff_mask()
        if not self.appear(self.I_AB_SELECTED_TEN):
            self.switch_to_floor_10()
            self.screenshot()
            if not self.appear(self.I_AB_SELECTED_TEN):
                raise GameStuckError('未能确认极十星')
            after = self._debuff_mask()
            for index, (wanted, actual) in enumerate(zip(before, after)):
                if wanted != actual:
                    x = 162 + (index % 6) * 80
                    y = 207 + (index // 6) * 81
                    self.device.click(x, y, control_name=f'restore_area_boss_debuff_{index}')
                    time.sleep(0.3)
            self.screenshot()
            if self._debuff_mask() != before:
                raise GameStuckError('切换十星后未能恢复原有减益')
        logger.info(f'已确认极十星，保留 {sum(before)} 项减益')

    def fight_open_detail_preserving_debuffs(self):
        self.ensure_ten_stars_preserving_debuffs()
        if not self.start_fight():
            raise AreaBossDefeated('地域鬼王挑战失败')
        if not self.wait_until_appear(self.I_AB_CLOSE_RED, wait_time=25):
            raise GameStuckError('战斗后没有返回鬼王详情')
        self.ui_click_until_disappear(self.I_AB_CLOSE_RED, interval=1)

    def _get_dynamic_boss_count(self) -> int:
        """
        从地域鬼王主界面 OCR 声望值，动态决定可挑战次数
        :return: 可挑战鬼王数量 (1/2/3)
        """
        self.screenshot()
        rep = self.O_AB_REPUTATION.ocr_digit(self.device.image)
        logger.info(f"Area boss reputation: {rep}")
        if rep >= 10000:
            return 3
        elif rep >= 2000:
            return 2
        else:
            return 1

    def run(self) -> bool:
        """
        运行脚本
        :return:
        """
        # 直接手动关闭这个锁定阵容的设置
        self.config.area_boss.general_battle.lock_team_enable = False
        con = self.config.area_boss.boss

        if con.daily_bounty_and_favorite:
            return self.run_daily_two_bosses()

        if self.config.area_boss.switch_soul.enable:
            self.ui_get_current_page()
            self.ui_goto(page_shikigami_records)
            self.run_switch_soul(self.config.area_boss.switch_soul.switch_group_team)

        if self.config.area_boss.switch_soul.enable_switch_by_name:
            self.ui_get_current_page()
            self.ui_goto(page_shikigami_records)
            self.run_switch_soul_by_name(self.config.area_boss.switch_soul.group_name,
                                         self.config.area_boss.switch_soul.team_name)

        self.ui_get_current_page()
        self.ui_goto(page_area_boss)

        # 已挑战鬼王数量
        boss_fought = 0
        if con.boss_reward:
            if self.fight_reward_boss():  # 挑战成功则加一
                boss_fought += 1

        self.open_filter()
        # 切换到对应集合(热门/收藏)
        if con.use_collect:
            self.switch_to_collect()
        else:
            self.switch_to_famous()

        # 动态获取可挑战次数
        dynamic_count = self._get_dynamic_boss_count()
        available = dynamic_count - boss_fought
        if available >= 3:
            self.boss_fight(self.I_BATTLE_1)
            self.boss_fight(self.I_BATTLE_2)
            self.boss_fight(self.I_BATTLE_3)
        elif available == 2:
            self.boss_fight(self.I_BATTLE_1)
            self.boss_fight(self.I_BATTLE_2)
        elif available == 1:
            self.boss_fight(self.I_BATTLE_1)
        # 退出
        self.go_back()
        self.set_next_run(task='AreaBoss', success=True, finish=False)

        # 以抛出异常的形式结束
        raise TaskEnd

    def go_back(self) -> None:
        """
        返回, 要求这个时候是出现在地域鬼王的主界面
        :return:
        """
        # 点击返回
        logger.info("Script back home")
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_UI_BACK_YELLOW, threshold=0.6, interval=2):
                continue
            if self.appear(self.I_CHECK_MAIN, threshold=0.6):
                break

    def boss(self, battle: RuleImage, collect: bool = False):

        # 点击右上角的鬼王选择
        logger.info("Script filter")
        while 1:
            self.screenshot()
            # 如果筛选界面已经打开 点击热门按钮
            if self.appear(self.I_AB_FILTER_OPENED):
                self.click(self.C_AB_FAMOUS_BTN)
                break
            if self.appear_then_click(self.I_FILTER, interval=3):
                continue

        if collect:
            self.switch_to_collect()
        # 页面没有可挑战的BOSS
        if not (self.appear(self.I_BATTLE_1) or self.appear(self.I_BATTLE_2) or self.appear(self.I_BATTLE_3)):
            logger.error("There is no boss could be challenged")
            return
        # 点击第几个鬼王
        logger.info(f'Script area boss {battle}')
        self.ui_click(battle, self.I_AB_CLOSE_RED)
        # 点击挑战
        logger.info("Script fire ")
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_FIRE, interval=1):
                continue
            if not self.appear(self.I_AB_CLOSE_RED):  # 如果这个红色的关闭不见了才可以进行继续
                break
        if not self.run_general_battle(self.config.area_boss.general_battle):
            logger.info("地域鬼王第2只战斗失败")
        # 红色关闭
        logger.info("Script close red")
        self.wait_until_appear(self.I_AB_CLOSE_RED)
        self.ui_click(self.I_AB_CLOSE_RED, self.I_FILTER)

    def boss_fight(self, battle: RuleImage, fileter_open: bool = True) -> bool:
        """
            完成挑战一个鬼王的全流程
            从打开筛选界面开始 到关闭鬼王详情界面结束
        @param battle: 挑战按钮,鬼王头像也可,只要点击能进入详情界面
        @type battle:
        @return:    True        挑战成功
                    False       挑战失败
        @rtype:
        """
        reward_floor = self.config.area_boss.boss.reward_floor
        if fileter_open and not self.appear(self.I_AB_FILTER_OPENED):
            self.open_filter()
        # 如果打不开鬼王详情界面,直接退出
        if not self.open_boss_detail(battle, 3):
            return False

        # 如果已经打过该BOSS,直接跳过不打了
        if self.is_group_ranked():
            logger.warning("There is no boss could be challenged")
            self.ui_click_until_disappear(self.I_AB_CLOSE_RED, interval=3)
            return True

        # 根据 reward_floor 决定模式
        if reward_floor in (AreaBossFloor.ONE, AreaBossFloor.TEN):
            # 极模式分支
            if self.setup_ultra(reward_floor):
                pass
        elif reward_floor == AreaBossFloor.NORMAL_LV60:
            # 普通模式-拉到60级
            self.setup_normal()
            self.switch_to_level_60()
        elif reward_floor == AreaBossFloor.NORMAL_LV1:
            # 普通模式-保持1级
            self.setup_normal()
        # DEFAULT: 不更改，直接打

        result = True
        if not self.start_fight():
            result = False
            logger.warning("Area Boss Fight Failed ")
        self.wait_until_appear(self.I_AB_CLOSE_RED)
        self.ui_click_until_disappear(self.I_AB_CLOSE_RED, interval=1)
        return result

    def start_fight(self) -> bool:
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_FIRE, interval=1):
                continue
            if not self.appear(self.I_AB_CLOSE_RED):  # 如果这个红色的关闭不见了才可以进行继续
                break

        return self.run_general_battle(self.config.area_boss.general_battle)

    def setup_ultra(self, floor: AreaBossFloor = AreaBossFloor.ONE) -> bool:
        # 确定进入鬼王界面
        self.wait_until_appear(self.I_AB_CLOSE_RED)
        # 尝试切换
        if not self.get_difficulty():
            # 如果可以切换，直接切换
            if self.appear(self.I_AB_DIFFICULTY_NORMAL):
                self.switch_difficulty(True)
            else:
                logger.warning("Cannot switch difficulty")
                return False
        # 调整极地鬼层数
        match floor:
            case AreaBossFloor.ONE:
                self.switch_to_floor_1()
            case AreaBossFloor.TEN:
                self.switch_to_floor_10()
        return True

    def setup_normal(self) -> bool:
        """
        确保当前为普通地鬼模式
        :return: True 成功（已处于普通模式），False 失败
        """
        self.wait_until_appear(self.I_AB_CLOSE_RED)
        if self.get_difficulty():
            # 当前是极地鬼，需要切回普通
            if self.appear(self.I_AB_DIFFICULTY_JI):
                self.switch_difficulty(False)
            else:
                logger.warning("Cannot switch to normal difficulty")
                return False
        return True

    def switch_to_level_60(self):
        logger.info("Switch to level 60")
        while 1:
            self.screenshot()
            if self.appear(self.I_AB_LEVEL_60):
                break
            if self.appear(self.I_AB_LEVEL_HANDLE):
                x, y = self.I_AB_LEVEL_HANDLE.front_center()
                self.S_AB_LEVEL_RIGHT.roi_front = (x, y, 10, 10)
                self.swipe(self.S_AB_LEVEL_RIGHT, interval=3)

    def get_difficulty(self) -> bool:
        """
        @return:    True           极地鬼
                    False           普通地鬼
        @rtype: bool
        """
        self.screenshot()
        return self.appear(self.I_AB_DIFFICULTY_JI)

    def switch_difficulty(self, ultra: bool = True):
        """
            切换普通地鬼/极地鬼
        @param ultra:  是否切换到极地鬼
                    True        切换到极地鬼
                    False       切换到普通地鬼
        @type ultra:
        """
        _from = self.I_AB_DIFFICULTY_NORMAL if ultra else self.I_AB_DIFFICULTY_JI
        _to = self.I_AB_DIFFICULTY_JI if ultra else self.I_AB_DIFFICULTY_NORMAL
        while 1:
            self.screenshot()
            if self.appear(_to):
                break
            if self.appear(_from):
                self.click(_from, interval=3)
                continue

    def switch_to_floor_1(self):
        """
            更改层数为一层
        """
        # _Floor = ["壹星", "贰星", "叁星", "肆星", "伍星", "陆星", "柒星", "捌星", "玖星", "拾星"]
        # 打开选择列表
        self.ui_click(self.C_AB_JI_FLOOR_SELECTED, self.I_AB_JI_FLOOR_LIST_CHECK, interval=3)
        while 1:
            self.screenshot()
            if self.appear(self.I_AB_JI_FLOOR_ONE):
                self.click(self.I_AB_JI_FLOOR_ONE)
                logger.info("Switch to floor 1")
                break
            self.swipe(self.S_AB_FLOOR_DOWN, interval=1)
            # 等待滑动动画
            self.wait_until_appear(self.I_AB_JI_FLOOR_ONE, False, 1)

    def switch_to_floor_10(self):
        """
            更改层数为十层
        """
        # 打开选择列表
        self.ui_click(self.C_AB_JI_FLOOR_SELECTED, self.I_AB_JI_FLOOR_LIST_CHECK, interval=3)
        while 1:
            self.screenshot()
            if self.appear(self.I_AB_JI_FLOOR_TEN):
                self.click(self.I_AB_JI_FLOOR_TEN)
                logger.info("Switch to floor 10")
                break
            self.wait_until_appear(self.I_AB_JI_FLOOR_TEN, False, 1)

    def fight_reward_boss(self):
        BOSS_REWARD_PHOTO1 = [self.C_AB_BOSS_REWARD_PHOTO_1, self.C_AB_BOSS_REWARD_PHOTO_2, self.C_AB_BOSS_REWARD_PHOTO_3]
        BOSS_REWARD_PHOTO2 = [self.C_AB_BOSS_REWARD_PHOTO_MINUS_2, self.C_AB_BOSS_REWARD_PHOTO_MINUS_1]
        need_open_filter, boss_name, photo = self.get_hot_in_reward()  # 获取挑战人数最多的Boss的名字
        if photo is None or boss_name == '声望不够':
            return False
        # 不需要打开筛选界面说明直接找到了目标boss, 直接挑战
        if not need_open_filter:
            return self.boss_fight(photo, fileter_open=False)
        # 滑动到最顶层
        logger.info("Swipe to top")
        for i in range(random.randint(1, 3)):
            self.swipe(self.S_AB_FILTER_DOWN)
        # 遍历所有boss找到名称一致的即目前挑战人数最多的
        for PHOTO in BOSS_REWARD_PHOTO1:
            self.open_filter()
            name = self.get_bossName(PHOTO)
            if self.check_common_chars(str(name), boss_name):
                return self.boss_fight(PHOTO, fileter_open=False)
            self.ui_click_until_disappear(self.I_AB_CLOSE_RED)
        # 倒数一和二
        for i in range(random.randint(1, 3)):
            self.swipe(self.S_AB_FILTER_UP)
        for PHOTO in BOSS_REWARD_PHOTO2:
            self.open_filter()
            name = self.get_bossName(PHOTO)
            if self.check_common_chars(str(name), boss_name):
                return self.boss_fight(PHOTO, fileter_open=False)
            self.ui_click_until_disappear(self.I_AB_CLOSE_RED)
        self.ui_click_until_disappear(self.I_AB_CLOSE_RED)

    def get_hot_in_reward(self):
        """
            返回挑战人数最多的悬赏鬼王
        @return: 是否打开筛选界面, boss名称, boss图片的click
        @rtype:
        """
        self.switch_to_reward()
        boss_configs = [
            {"photo": self.C_AB_BOSS_REWARD_PHOTO_1, "need_swipe": False},
            {"photo": self.C_AB_BOSS_REWARD_PHOTO_2, "need_swipe": False},
            {"photo": self.C_AB_BOSS_REWARD_PHOTO_3, "need_swipe": False},
            {"photo": self.C_AB_BOSS_REWARD_PHOTO_MINUS_2, "need_swipe": True},
            {"photo": self.C_AB_BOSS_REWARD_PHOTO_MINUS_1, "need_swipe": True},
        ]

        def check_boss(photo: RuleClick):
            """
            检查boss是否满足条件
            :param photo:
            :return: 是否满足条件, 挑战数量, boss名称
            """
            self.open_filter()
            num = self.get_num_challenge(photo) or 0
            if not num:
                name = '声望不够'
            else:
                name = self.get_bossName(photo)
                if num >= 20000 and not self.appear(self.I_AB_NUM_CHALLENGE_RAIL):
                    logger.info("The number of challenges is enough")
                    return True, num, name
            # 没找到满足的则关闭boss页面
            self.ui_click_until_disappear(self.I_AB_CLOSE_RED)
            return False, num, name

        mx_challenge_boss_name = None
        mx_challenge_num = 0
        photo = None
        # 遍历所有boss配置, 找挑战人数最多的boss
        for cfg in boss_configs:
            if cfg["need_swipe"]:
                self.open_filter()
                for _ in range(random.randint(1, 3)):
                    self.swipe(self.S_AB_FILTER_UP)
                self.wait_until_appear(cfg["photo"], wait_time=1)
            ret, challenge_num, boss_name = check_boss(cfg["photo"])
            if ret:  # 直接找到满足条件的, 则不需要打开筛选界面直接挑战即可
                return False, boss_name, cfg["photo"]
            if challenge_num > mx_challenge_num:
                mx_challenge_num = challenge_num
                mx_challenge_boss_name = boss_name
                photo = cfg['photo']
                logger.attr(mx_challenge_num, f'Select:{boss_name},{photo.name}')
        return True, mx_challenge_boss_name if mx_challenge_boss_name else '声望不够', photo if mx_challenge_boss_name else None

    def get_num_challenge(self, click_area):
        """
            获取鬼王挑战人数
        @param click_area: 鬼王相应的挑战按钮
        @type click_area:
        @return:
        @rtype:
        """
        # 如果鬼王不可挑战(未解锁),限制3次尝试打开鬼王详情界面
        if not self.open_boss_detail(click_area, 3):
            logger.info("%s unavailable", str(click_area))
            return 0
        return self.O_AB_NUM_OF_CHALLENGE.ocr_digit(self.device.image)

    def get_bossName(self, click_area):
        """
            获取鬼王名字
        @param click_area: 鬼王相应的挑战按钮
        @type click_area:
        @return:
        @rtype:
        """
        # 如果鬼王不可挑战(未解锁),限制3次尝试打开鬼王详情界面
        if not self.open_boss_detail(click_area, 3):
            logger.info("%s unavailable", str(click_area))
            return 0
        ocrName = self.O_AB_BOSS_NAME.detect_and_ocr(self.device.image)
        bossName = re.sub(r"[\'\[\]]", "", str([result.ocr_text for result in ocrName]))
        return bossName

    def open_boss_detail(self, battle: RuleImage, try_num: int = 3) -> bool:
        """
            打开鬼王详情界面
        @param battle:
        @type battle:
        @param try_num: 重试次数
        @type try_num:
        @return:    True        打开成功
                    False       打开失败
        @rtype:
        """
        try_count = 0
        while 1:
            self.screenshot()
            if self.appear(self.I_AB_CLOSE_RED) and self.appear(self.I_FIRE):
                self.screenshot()
                if not self.appear(self.I_FIRE):
                    continue
                return True
            if try_count >= try_num:
                logger.warning(f"Cannot boss_detail, try {try_count} times")
                return False
            if self.click(battle, interval=3):
                try_count += 1
                continue
        return True

    def is_group_ranked(self):
        """
            判断该鬼王是否已经获取到小组排名
        """
        return not self.appear(self.I_AB_GROUP_RANK_NONE)
        pass

    def open_filter(self):
        """打开筛选界面"""
        logger.info("openFilter")
        self.ui_click(self.I_FILTER, self.I_AB_FILTER_OPENED, interval=3)

    def switch_to_collect(self):
        while 1:
            self.screenshot()
            if self.appear(self.I_AB_FILTER_TITLE_COLLECTION):
                break
            if self.appear(self.I_AB_FILTER_OPENED):
                self.click(self.C_AB_COLLECTION_BTN, 1.5)
                continue

    def switch_to_famous(self):
        while 1:
            self.screenshot()
            if self.appear(self.I_AB_FILTER_TITLE_FAMOUS):
                break
            if self.appear(self.I_AB_FILTER_OPENED):
                self.click(self.C_AB_FAMOUS_BTN, 1.5)
                continue

    def switch_to_reward(self):
        self.open_filter()
        while 1:
            self.screenshot()
            if self.appear(self.I_AB_FILTER_TITLE_REWARD):
                break
            if self.appear(self.I_AB_FILTER_OPENED):
                self.click(self.C_AB_REWARD_BTN, 1.5)
                continue

    def check_common_chars(self, bossName, name):
        # 将两个字符串转为集合，去除重复的字符
        set_boss = set(bossName)
        set_name = set(name)

        # 计算交集，判断交集的元素个数
        common_chars = set_boss & set_name  # & 是集合的交集运算符

        if len(common_chars) >= 2:
            return 1
        else:
            return 0  # 如果交集的字符少于2个，可以根据需要返回其他值
if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    # time.sleep(3)
    # t.switchFloor2One()
    # t.switch2Level60()
    t.run()
