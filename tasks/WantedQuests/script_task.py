# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta, time, datetime
from time import sleep, monotonic
from typing import List

import re
import cv2
from cached_property import cached_property

from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.base.timer import Timer
from module.exception import TaskEnd, GameStuckError
from module.logger import logger
from tasks.Component.Costume.config import MainType
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.GameUi.page import page_main, page_exploration, page_shikigami_records
from tasks.Secret.script_task import ScriptTask as SecretScriptTask
from tasks.WantedQuests.assets import WantedQuestsAssets
from tasks.WantedQuests.config import CooperationType, CooperationSelectMask
from tasks.WantedQuests.explore import WQExplore, ExploreWantedBoss
from importlib import reload
from tasks.WantedQuests import board_state

# Task modules are loaded afresh for each scheduled run, but support modules
# remain cached in the long-running worker. Refresh this small vision module so
# updated board templates take effect without interrupting other tasks.
board_state = reload(board_state)
sealed_page_has_next = board_state.sealed_page_has_next
sealed_page_is_last = board_state.sealed_page_is_last
completed_reward_button = board_state.completed_reward_button


class SecretSpeedEncountered(Exception):
    """A bounty route entered a secret speed challenge."""


class ScriptTask(WQExplore, SecretScriptTask, WantedQuestsAssets):
    I_SECRET_SPEED = RuleImage(roi_front=(1002,140,159,218), roi_back=(1002,140,159,218), threshold=0.8, method='Template matching', file='./tasks/WantedQuests/wq/wq_secret_speed.png')
    I_TRACE_ENABLE_CURRENT = RuleImage(roi_front=(1146,598,79,76), roi_back=(1100,570,150,130), threshold=0.8, method='Template matching', file='./tasks/WantedQuests/wq/wq_trace_enable_current.png')
    I_TRACE_DISABLE_CURRENT = RuleImage(roi_front=(1146,598,79,76), roi_back=(1100,570,150,130), threshold=0.8, method='Template matching', file='./tasks/WantedQuests/wq/wq_trace_disable_current.png')
    I_DETAIL_TRACED_CURRENT = RuleImage(roi_front=(1147,556,79,76), roi_back=(1110,530,135,125), threshold=0.8, method='Template matching', file='./tasks/WantedQuests/wq/wq_detail_traced_current.png')
    def preset_already_equipped(self):
        if self.appear(self.I_SOU_ALREADY_EQUIPPED):
            return True
        ocr = RuleOcr(roi=(380,210,510,65), area=(380,210,510,65), mode='Full', method='Default', keyword='', name='wanted_soul_equipped')
        return any('全队正在使用预设御魂' in ''.join(item.ocr_text.split()) for item in ocr.detect_and_ocr(self.device.image))
    want_strategy_excluding: list[list] = []  # 不需要执行的
    # 追踪界面(显示"前往"按钮的界面,左上角位置,神秘任务不好使)显示以下名称时,任务不再执行
    unwanted_boss_name_list: list = []

    def run(self):
        self._secret_speed_excluded = set()
        self.want_strategy_excluding = []
        self.unwanted_boss_name_list = []
        con = self.config.model.wanted_quests
        unwanted_boss_names = con.wanted_quests_config.unwanted_boss_names
        if unwanted_boss_names is not None and unwanted_boss_names != '':
            import re
            self.unwanted_boss_name_list = re.split(r"[，,]", unwanted_boss_names)

        # 自动换御魂
        if con.switch_soul_config.enable:
            self.ui_get_current_page()
            self.ui_goto(page_shikigami_records)
            self.run_switch_soul(con.switch_soul_config.switch_group_team)
        if con.switch_soul_config.enable_switch_by_name:
            self.ui_get_current_page()
            self.ui_goto(page_shikigami_records)
            self.run_switch_soul_by_name(con.switch_soul_config.group_name, con.switch_soul_config.team_name)

        preSuc = False
        if (self.get_config()).cooperation_only:
            preSuc = self.pre_work_cooperation_only()
        else:
            preSuc = self.pre_work()
        if not preSuc:
            # An unrecognized board is not evidence that quests are complete.
            logger.error('悬赏封印界面未能识别，任务没有确认完成')
            self.device.save_screenshot(genre='wanted_quests_prework', interval=1)
            self.set_next_run(task='WantedQuests', finish=True, server=False,
                              target=datetime.now() + timedelta(minutes=30))
            raise TaskEnd('WantedQuests')

        if not self.complete_traced_quests():
            logger.error('悬赏尚未完成，30 分钟后重试')
            self.set_next_run(task='WantedQuests', finish=True, server=False,
                              target=datetime.now() + timedelta(minutes=30))
            raise TaskEnd('WantedQuests')
        self.next_run()
        raise TaskEnd('WantedQuests')

    def complete_traced_quests(self, strict=False):
        """Complete the currently traced tasks, keeping sender work isolated."""
        self._wanted_clue_skipped = False
        self.screenshot()
        number_challenge = self.O_WQ_NUMBER.ocr(self.device.image)
        error_count = 0
        saw_progress = False
        while 1:
            self.screenshot()
            if not self.is_wq_remained():
                logger.info("no more wq remained")
                if strict and not saw_progress:
                    raise GameStuckError('Cannot confirm tracked sender quests; no progress visible')
                return True
            if self.appear(self.I_WQ_BOX):
                logger.info("get reward")
                self.ui_get_reward(self.I_WQ_BOX)
                continue
            if self.appear(self.I_TREASURE_BOX_CLICK):
                logger.info("get treasure")
                self.ui_get_reward(self.I_TREASURE_BOX_CLICK)
                continue
            if error_count > 3:
                logger.warning('failed too many times, exit')
                return False
            if self.current_count >= 30:
                logger.error(f'current count {self.current_count} >= 20, exit')
                raise Exception('current count >= 20, exit')
            cu, re, total, area = self.find_wq(self.device.image, strict_progress=strict)
            logger.info(f"find_wq result: current {cu} remain {re} total {total} area {area}")
            if re == -2:
                if strict and getattr(self, '_wanted_clue_skipped', False):
                    raise GameStuckError('存在跳过的线索悬赏，无法确认追踪任务全部完成')
                logger.info("only completed wanted quests remained")
                return True
            if re == -1:
                error_count += 1
                # 没找到任务 尝试上滑
                self.swipe(self.S_WQ_LIST_UP, interval=1)
                sleep(1)
                continue
            # 找到任务,执行
            error_count = 0
            saw_progress = True
            self.O_WQ_TEXT_ALL.area = area
            result = self.execute_mission(self.O_WQ_TEXT_ALL, total - cu, number_challenge)
            if result is False:
                return False
            sleep(1.5)


    def next_run(self):
        fixed_times = self.get_config().fixed_run_times.strip()
        if fixed_times:
            now = datetime.now()
            times = [time.fromisoformat(value.strip()) for value in fixed_times.split(',') if value.strip()]
            if not times:
                raise ValueError('WantedQuests fixed run times must not be empty')
            candidates = [datetime.combine(now.date() + timedelta(days=day), value)
                          for day in (0, 1) for value in times]
            target = min(value for value in candidates if value > now)
            self.set_next_run(task='WantedQuests', finish=True, server=False, target=target)
            return
        before_end: time = self.get_config().before_end
        if before_end == time(hour=0, minute=0, second=0):
            self.set_next_run(task='WantedQuests', success=True, finish=True)
            return
        time_delta = timedelta(hours=-before_end.hour, minutes=-before_end.minute, seconds=-before_end.second)
        now_datetime = datetime.now()
        now_time = now_datetime.time()
        if time(hour=5) <= now_time < time(hour=18):
            # 如果是在5点到18点之间，那就设定下一次运行的时间为第二天的5点 + before_end
            next_run_datetime = datetime.combine(now_datetime.date() + timedelta(days=1), time(hour=5))
            next_run_datetime = next_run_datetime + time_delta
        elif time(hour=18) <= now_time < time(hour=23, minute=59, second=59):
            # 如果是在18点到23点59分59秒之间，那就设定下一次运行的时间为第二天的18点 + before_end
            next_run_datetime = datetime.combine(now_datetime.date() + timedelta(days=1), time(hour=18))
            next_run_datetime = next_run_datetime + time_delta
        else:
            # 如果是在0点到5点之间，那就设定下一次运行的时间为今天的18点 + before_end
            next_run_datetime = datetime.combine(now_datetime.date(), time(hour=18))
            next_run_datetime = next_run_datetime + time_delta
        self.set_next_run(task='WantedQuests', target=next_run_datetime)

    def pre_work(self):
        """
        前置工作，
        :return:
        """
        self.ui_get_current_page()
        self.ui_goto(page_main)
        done_timer = Timer(15)
        sealed_pages_turned = 0
        last_page_turn = 0.0
        last_reward_click = 0.0
        reward_clicks = 0
        while 1:
            self.screenshot()
            if self.ui_reward_appear_click():
                logger.info('关闭悬赏领奖弹窗')
                sleep(.5)
                continue
            reward_button = completed_reward_button(self.device.image)
            if reward_button:
                if monotonic() - last_reward_click >= 3:
                    if reward_clicks >= 3:
                        logger.warning('悬赏领奖按钮重复出现，稍后重试')
                        self.device.save_screenshot(genre='wanted_reward_unconfirmed', interval=0)
                        return False
                    logger.info('领取已完成的悬赏奖励')
                    self.device.click(*reward_button, control_name='wanted_completed_reward')
                    last_reward_click = monotonic()
                    reward_clicks += 1
                    done_timer.reset()
                sleep(.3)
                continue
            reward_clicks = 0
            if self.appear(self.I_TRACE_DISABLE) or self.appear(self.I_TRACE_DISABLE_CURRENT):
                break
            if self.appear_then_click(self.I_WQ_SEAL, interval=1):
                continue
            if self.appear_then_click_multi_scale(self.I_WQ_DONE,scale_range=(0.8, 1.2) ,interval=1):
                continue
            if self.appear_then_click(self.I_TRACE_ENABLE, interval=1):
                continue
            if self.appear_then_click(self.I_TRACE_ENABLE_CURRENT, interval=1):
                continue
            if sealed_pages_turned and sealed_page_is_last(self.device.image):
                logger.info('末页悬赏均已封印，检查已追踪任务')
                break
            if sealed_page_has_next(self.device.image):
                # A sealed page is not proof that the following pages are done.
                # Give animations time to settle and stop after bounded attempts.
                if sealed_pages_turned < 5 and monotonic() - last_page_turn >= 3:
                    logger.info('当前四张悬赏均已封印，检查下一页')
                    # The chevrons indicate horizontal scrolling; tapping
                    # them does not turn the current board in this layout.
                    self.device.swipe((1080, 370), (380, 370), duration=.8,
                                      control_name='wanted_board_next_page')
                    sealed_pages_turned += 1
                    last_page_turn = monotonic()
                    done_timer.reset()
                    sleep(1)
                    continue
            if self.special_main and self.click(self.C_SPECIAL_MAIN, interval=3):
                logger.info('Click special main left to find wanted quests')
                continue
            if self.appear(self.I_UI_BACK_RED):
                if not done_timer.started():
                    done_timer.start()
            if done_timer.started() and done_timer.reached():
                self.device.save_screenshot(genre='wanted_quests_board_unrecognized', interval=1)
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
                return False
        # 已追踪所有任务
        logger.info('All wanted quests are traced')

        # 存在协作任务则邀请
        self.screenshot()
        if self.appear(self.I_WQ_INVITE_1) or self.appear(self.I_WQ_INVITE_2) or self.appear(self.I_WQ_INVITE_3):
            if self.need_invite_vip():
                self.all_cooperation_invite()
            else:
                self.invite_five()
        self.ui_click_until_disappear(self.I_UI_BACK_RED)
        self.ui_goto(page_exploration)
        return True

    def open_cooperation_board(self):
        #
        if self.ui_get_current_page() != page_main:
            self.ui_goto(page_main)
        # 打开悬赏封印 界面
        done_timer = Timer(5)
        deadline = monotonic() + 45
        while 1:
            if monotonic() >= deadline:
                raise GameStuckError('Timed out opening cooperation quest board')
            self.screenshot()
            if self.appear(self.I_TRACE_ENABLE) or self.appear(self.I_TRACE_DISABLE):
                break
            if self.appear_then_click(self.I_WQ_SEAL, interval=1):
                continue
            if self.appear_then_click_multi_scale(self.I_WQ_DONE,scale_range=(0.8, 1.2), interval=1):
                continue
            if self.special_main and self.click(self.C_SPECIAL_MAIN, interval=3):
                logger.info('Click special main left to find wanted quests')
                continue
            if self.appear(self.I_UI_BACK_RED):
                if not done_timer.started():
                    done_timer.start()
            if done_timer.started() and done_timer.reached():
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
                return False
        return True

    def pre_work_cooperation_only(self):
        if not self.open_cooperation_board():
            return False
        #
        if not (self.appear(self.I_WQ_INVITE_1) or self.appear(self.I_WQ_INVITE_2) or self.appear(self.I_WQ_INVITE_3)):
            logger.info("there is no cooperation quest")
            return False

        # if self.appear(self.I_WQ_INVITE_1):
        #     self.trace_one(self.I_WQ_INVITE_1)
        # if self.appear(self.I_WQ_INVITE_2):
        #     self.trace_one(self.I_WQ_INVITE_2)
        # if self.appear(self.I_WQ_INVITE_3):
        #     self.trace_one(self.I_WQ_INVITE_3)

        # 追踪任务 并邀请
        self.all_cooperation_invite()

        self.ui_click_until_disappear(self.I_UI_BACK_RED)
        self.ui_goto(page_exploration)
        return True

    def prepare_sender_cooperation(self):
        """Clear old tracked quests before tracking only successful shares."""
        self.screenshot()
        # "Track all" can coexist with a partially tracked old task list.
        # Toggle all on, then all off, before selecting successful shares.
        if self.appear(self.I_TRACE_ENABLE):
            if not self.ui_click(self.I_TRACE_ENABLE, self.I_TRACE_DISABLE, interval=1, timeout=10):
                raise GameStuckError('Cannot normalize previous quest tracking')
        if self.appear(self.I_TRACE_DISABLE):
            if not self.ui_click(self.I_TRACE_DISABLE, self.I_TRACE_ENABLE, interval=1, timeout=10):
                raise GameStuckError('Cannot clear previous quest tracking')
        if not self.appear(self.I_TRACE_ENABLE):
            raise GameStuckError('Cannot confirm clean quest tracking before invitations')

    def finish_sender_cooperation(self):
        self.ui_click_until_disappear(self.I_UI_BACK_RED)
        if not self.ui_goto(page_exploration):
            raise GameStuckError('Cannot reach exploration to complete shared quests')
        self.unwanted_boss_name_list = []
        self.want_strategy_excluding = []
        if not self.complete_traced_quests(strict=True):
            raise GameStuckError('Sender cooperation quests are still unfinished')

    def trace_one(self, btn: RuleImage):
        """Trace one ordinary quest and confirm it before returning."""
        deadline = monotonic() + 15
        attempted = False
        last_detail_click = 0
        while monotonic() < deadline:
            self.screenshot()
            if self.appear(self.I_WQ_TRACE_ONE_REALWORLD):
                self.close_cooperation_detail()
                return False
            if self.appear(self.I_WQ_TRACE_ONE_ENABLE):
                self.close_cooperation_detail()
                return True
            if self.appear(self.I_WQ_TRACE_ONE_DISABLE):
                self.click(self.I_WQ_TRACE_ONE_DISABLE, interval=1)
                continue
            board_visible = self.appear(self.I_TRACE_ENABLE) or self.appear(self.I_TRACE_DISABLE)
            if getattr(self,'black_gold_skin',False):
                if board_visible and monotonic()-last_detail_click>=2:
                    x,y,w,h=btn.roi_front
                    slot=(x-90)//282
                    self.device.click(220+282*slot,230,control_name='trace_shared_cooperation')
                    last_detail_click=monotonic()
                continue
            if (self.appear(btn, interval=1.5)
                    or (not attempted and board_visible)):
                x,y,w,h = btn.roi_front
                if getattr(self, 'black_gold_skin', False):
                    slot = (x-90)//282
                    self.device.click(220+282*slot,230,control_name='trace_shared_cooperation')
                else:
                    self.device.click(x+w//2,y-40,control_name='trace_shared_cooperation')
                attempted = True
        raise GameStuckError('Cannot confirm tracking for shared cooperation quest')

    def execute_mission(self, ocr, num_want: int, num_challenge: int):
        """

        :param ocr: 要点击的 文字
        :param num_want: 一共要打败的怪物数量
        :param num_challenge: 现在有的挑战卷数量
        :return:
        """
        OCR_WQ_TYPE = [self.O_WQ_TYPE_1, self.O_WQ_TYPE_2, self.O_WQ_TYPE_3, self.O_WQ_TYPE_4]
        OCR_WQ_INFO = [self.O_WQ_INFO_1, self.O_WQ_INFO_2, self.O_WQ_INFO_3, self.O_WQ_INFO_4]
        GOTO_BUTTON = [self.I_GOTO_1, self.I_GOTO_2, self.I_GOTO_3, self.I_GOTO_4]
        name_funcs: dict = {
            '式神': self.challenge,
            '探索': self.explore,
            '秘闻': self.secret
        }

        def extract_info(index: int) -> tuple or None:
            """
            提取每一个地点的信息
            :param index: 从零开始
            :return:
            (type, destination, number, goto_button, func)
            (类型, 地点层级，可以打败的数量，前往按钮, func)
            类型： 挑战0, 秘闻1， 探索2
            """
            # 获取用户设置的值
            user_limit = self.config.model.wanted_quests.wanted_quests_config.layer_limit.value            
            # 定义完整的层数后缀顺序
            all_layers = ["壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖", "拾", "番外"]
            # 根据用户选择进行截取，生成 layer_limit 集合
            if user_limit == "无限制":
                layer_limit = set()
            else:
                start_idx = all_layers.index(user_limit) if user_limit in all_layers else 6
                # 截取该层及之后的所有层
                layer_limit = set(all_layers[start_idx:])

            # ,荒川之怒·壹，4，前往按钮，function
            result = [-1, '', -1, GOTO_BUTTON[index], self.challenge, '']
            if not self.appear(GOTO_BUTTON[index]):
                return None
            type_wq = OCR_WQ_TYPE[index].ocr(self.device.image)
            if type_wq == '闻':
                type_wq = '秘闻'
            if current_detail:
                y = (282, 357, 432, 507)[index]
                fragment_label = RuleImage(roi_front=(636,y,118,35), roi_back=(632,y-4,126,43),
                    threshold=0.83, method='Template matching',
                    file='./tasks/WantedQuests/wq/wq_fragment_current.png')
                if self.appear(fragment_label):
                    type_wq = '式神'
            info_wq_1 = OCR_WQ_INFO[index].ocr(self.device.image)
            info_wq_1 = info_wq_1.replace('：', ':').replace('（', '(').replace('）', ')')
            info_wq_1 = info_wq_1.replace('：', ':')
            match = re.match(r"^(.*?)[（(]?数量[：:]\s*(\d+)[)）]", info_wq_1)
            if not match:
                return None
            wq_destination = match.group(1)
            wq_number = int(match.group(2))
            if not wq_destination or wq_number <= 0:
                return None
            if current_detail and type_wq == '式神':
                chapter = re.search(r'第[一二三四五六七八九十百\d]+章', wq_destination)
                if chapter:
                    wq_destination = chapter.group()
            # 跳过高层秘闻
            if type_wq == '秘闻' and any(wq_destination.endswith(layer) for layer in layer_limit):
                logger.warning('This secret layer is too high')
                return None
            result[1] = wq_destination
            result[2] = wq_number
            order_list = self.config.model.wanted_quests.wanted_quests_config.battle_priority
            order_list = order_list.replace(' ', '').replace('\n', '')
            order_list: list = re.split(r'>', order_list)
            # OCR识别"式神"但用户配置用"挑战"，做映射
            type_wq_for_order = '挑战' if type_wq == '式神' else type_wq
            result[0] = order_list.index(type_wq_for_order) if type_wq_for_order in order_list else -1
            result[4] = name_funcs.get(type_wq, lambda: logger.warning('No task can be challenged'))
            result[5] = type_wq
            logger.info(f'[Wanted Quests] type: {type_wq} destination: {wq_destination} number: {wq_number} ')
            return tuple(result) if result[0] != -1 else None

        logger.hr('Start wanted quests')
        deadline = monotonic() + 12
        current_detail = False
        while monotonic() < deadline:
            self.screenshot()
            if self.appear(self.I_TRACE_TRUE):
                break
            if self.appear(self.I_DETAIL_TRACED_CURRENT):
                current_detail = True
                break
            if self.click(ocr, interval=1):
                continue
        else:
            raise GameStuckError('无法识别悬赏任务详情，停止重复点击')
        if current_detail:
            OCR_WQ_TYPE = [RuleOcr(roi=(636,y,73,35), area=(636,y,73,35), mode='Single', method='Default', keyword='', name=f'wq_new_type_{i}') for i,y in enumerate((282,357,432,507), 1)]
            OCR_WQ_INFO = [RuleOcr(roi=(716,y,315,38), area=(716,y,315,38), mode='Single', method='Default', keyword='', name=f'wq_new_info_{i}') for i,y in enumerate((282,357,432,507), 1)]
            GOTO_BUTTON = [RuleImage(roi_front=(1060,y,86,34), roi_back=(1048,y-8,110,52), threshold=0.8, method='Template matching', file='./tasks/WantedQuests/wq/wq_goto_current.png') for y in (284,359,434,509)]
        if not any(self.appear(button) for button in GOTO_BUTTON):
            # 如果没有出现 '前往'按钮， 那就是这个可能是神秘任务但是没有解锁
            logger.warning('This is a secret mission but not unlock')
            if current_detail:
                self.device.save_screenshot(genre='wanted_detail_no_goto', interval=0)
                logger.error('新版悬赏详情没有可识别的前往按钮，暂缓任务')
                return False
            self.ui_click(self.I_TRACE_TRUE, self.I_TRACE_FALSE)
            return False
        # 跳过不想打的
        monster_name = (RuleOcr(roi=(635,155,320,55), area=(635,155,320,55), mode='Single', method='Default', keyword='', name='wq_new_monster').ocr_single(self.device.image) if current_detail else self.O_WQ_MONSTER_TYPE.detect_text(self.device.image))
        if any(name and name in monster_name for name in self.unwanted_boss_name_list):
            #
            logger.warning(f'unwanted {monster_name}')
            if current_detail:
                self.click(self.I_DETAIL_TRACED_CURRENT)
            else:
                self.ui_click(self.I_TRACE_TRUE, self.I_TRACE_FALSE)
            return False

        info_wq_list = []
        for i in range(4):
            info_wq = extract_info(i)
            if info_wq:
                info_wq_list.append(info_wq)
        info_wq_list = [item for item in info_wq_list if item not in self.want_strategy_excluding
                        and (item[5], item[1]) not in getattr(self, '_secret_speed_excluded', set())]
        if not info_wq_list:
            logger.warning('No wanted quests can be challenged')
            if current_detail:
                logger.error('新版悬赏详情没有可执行的路线，暂缓任务')
                return False
            self.ui_click(self.I_TRACE_TRUE, self.I_TRACE_FALSE)
            return False
        # sort
        info_wq_list.sort(key=lambda x: x[0])
        filtered = list(filter(lambda x: (x[5] == '秘闻' or x[5] == '式神') and x[2] >= 3, info_wq_list))
        if not filtered and len(filtered) != 0:
            info_wq_list = filtered
        best_type, destination, once_number, goto_button, func, _ = info_wq_list[0]
        do_number = 1 if once_number >= num_want else num_want // once_number + (1 if num_want % once_number > 0 else 0)
        try:
            func(goto_button, do_number)
        except SecretSpeedEncountered:
            logger.warning('Secret speed challenge detected; return to courtyard and recheck bounties')
            if not hasattr(self, '_secret_speed_excluded'):
                self._secret_speed_excluded = set()
            self._secret_speed_excluded.add((info_wq_list[0][5], info_wq_list[0][1]))
            self.recover_secret_speed()
        except ExploreWantedBoss:
            logger.warning('The extreme case. The quest only needs to challenge one final boss, so skip it')
            self.want_strategy_excluding.append(info_wq_list[0])

    def challenge(self, goto_btn, num):
        self.ui_click(goto_btn, self.I_WQC_FIRE)
        self.ui_click(self.I_WQC_UNLOCK, self.I_WQC_LOCK)
        self.ui_click_until_disappear(self.I_WQC_FIRE)
        # 锁定阵容进入战斗
        wq_config = GeneralBattleConfig(lock_team_enable=True)
        self.run_general_battle(config=wq_config)
        self.wait_until_appear(self.I_WQC_FIRE, wait_time=4)
        # 关闭 挑战界面
        while 1:
            self.screenshot()
            if self.appear(self.I_CHECK_EXPLORATION):
                break
            if self.appear_then_click(self.I_UI_BACK_YELLOW, interval=1.5):
                continue

    def recover_secret_speed(self):
        deadline = monotonic() + 20
        while monotonic() < deadline:
            self.screenshot()
            if not self.appear(self.I_SECRET_SPEED):
                break
            self.appear_then_click(self.I_UI_BACK_BLUE, interval=1.5)
        else:
            raise GameStuckError('Cannot exit secret speed challenge')
        self.ui_get_current_page(skip_first_screenshot=False)
        if not self.ui_goto(page_main):
            raise GameStuckError('Cannot return to courtyard from secret speed challenge')
        if not self.pre_work():
            raise GameStuckError('Cannot reopen bounty board after secret speed challenge')

    def battle_wait(self, random_click_swipt_enable):
        if not getattr(self, '_wanted_secret_battle', False):
            # MRO includes SecretScriptTask, whose battle_wait omits auto-mode
            # checks. Exploration/challenge/soul battles must use the common
            # controller explicitly, not the secret-zone implementation.
            return GeneralBattle.battle_wait(self, random_click_swipt_enable)
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        logger.info('Start bounty secret battle process')
        while True:
            self.screenshot()
            if self.appear(self.I_SECRET_SPEED):
                raise SecretSpeedEncountered()
            if self.appear(self.I_SE_BATTLE_WIN):
                self.ui_click_until_disappear(self.I_SE_BATTLE_WIN, interval=2)
                return True
            if self.appear_then_click(self.I_WIN, interval=1):
                continue
            if self.appear(self.I_REWARD):
                self.ui_click_until_disappear(self.I_REWARD)
                return True
            if self.appear(self.I_FALSE):
                self.ui_click_until_disappear(self.I_FALSE)
                return False

    def secret(self, goto, num=1):
        self.ui_click(goto, self.I_WQSE_FIRE)
        self.screenshot()
        if self.appear(self.I_SECRET_SPEED):
            raise SecretSpeedEncountered()
        for i in range(num):
            self.wait_until_appear(self.I_WQSE_FIRE)
            # self.ui_click_until_disappear(self.I_WQSE_FIRE)
            # 又臭又长的对话针的是服了这个网易
            click_count = 0
            while 1:
                self.screenshot()
                if not self.appear(self.I_UI_BACK_RED, threshold=0.7):
                    break
                if self.appear_then_click(self.I_WQSE_FIRE, interval=1):
                    continue
                if self.appear(self.I_UI_BACK_RED, threshold=0.7) and not self.appear(self.I_WQSE_FIRE):
                    self.click(self.C_SECRET_CHAT, interval=0.8)
                    click_count += 1
                    if click_count >= 6:
                        logger.warning('Secret mission chat too long, force to close')
                        click_count = 0
                        self.device.click_record_clear()
                    continue
            self._wanted_secret_battle = True
            try:
                success = self.run_general_battle(self.battle_config)
            finally:
                self._wanted_secret_battle = False
        while 1:
            self.screenshot()
            if self.appear(self.I_CHECK_SECRET_ZONES):
                break
            if self.appear_then_click(self.I_UI_BACK_RED, interval=1):
                continue
            if self.appear_then_click(self.I_UI_BACK_BLUE, interval=1.5):
                continue
        self.ui_get_current_page()
        self.ui_goto(page_exploration)
        self.wait_until_stable(self.I_CHECK_EXPLORATION)
        logger.info('Secret mission finished')

    def invite_random(self, add_button: RuleImage):
        self.screenshot()
        if not self.appear(add_button):
            return False
        self.ui_click(add_button, self.I_WQ_INVITE_ENSURE, interval=2.5)
        logger.info('enter invite form')
        sleep(1)
        self.click(self.I_WQ_FRIEND_1)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_2)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_3)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_4)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_5)
        sleep(0.2)
        self.screenshot()
        if not self.appear(self.I_SELECTED):
            logger.warning('No friend selected')
            return False
        self.ui_click_until_disappear(self.I_INVITE_ENSURE)
        sleep(0.5)

    def invite_five(self):
        """
        邀请好友，默认点五个
        :return:
        """

        logger.hr('Invite friends')
        self.invite_random(self.I_WQ_INVITE_1)
        self.invite_random(self.I_WQ_INVITE_2)
        self.invite_random(self.I_WQ_INVITE_3)

    def all_cooperation_invite(self, name_all: str = None):
        """
            所有的协作任务依次邀请
            如果配置了只完成协作任务 还会将该任务设置为追踪
        @return:

        """
        self.screenshot()
        if not any(self.appear(getattr(self, f'I_WQ_INVITE_{i}')) for i in range(1, 4)):
            return False

        ret = self.get_cooperation_info()
        if len(ret) == 0:
            logger.info("no Cooperation found")
            return False
        typeMask = 15
        typeMask = CooperationSelectMask[(self.get_config()).cooperation_type.value]
        for item in ret:
            # 该任务是需要邀请的任务类型
            if not (item['type'] & typeMask):
                logger.info("cooperationType %s But needed Type %s ,Skipped", item['type'], typeMask)
                continue
            # A prior invitation may reorder the board. Re-read this slot before
            # using its coordinates; FindJade also filters out real-world quests.
            current = self.get_cooperation_info()
            item = next((entry for entry in current if entry['slot'] == item['slot']
                         and entry['type'] == item['type']), None)
            if item is None:
                logger.info('Cooperation slot changed after invitation; skipped')
                continue
            '''
               尝试5次 如果邀请失败 等待20s 重新尝试
               阴阳师BUG: 好友明明在线 但邀请界面找不到该好友(好友未接受任何协作任务的情况下)
           '''
            index = 0
            item['inviteResult'] = False
            if name_all is None:
                name = self.get_invite_vip_name(item['type'])
            else:
                name = name_all
            if not name:
                logger.info('No recipient needs cooperation type %s; skipped', item['type'])
                continue
            logger.warning("find cooperationType %s ,start invite %s", item['type'], name)
            while index < 5:
                if index:
                    current = self.get_cooperation_info()
                    retry_item = next((entry for entry in current if entry['slot'] == item['slot']
                                       and entry['type'] == item['type']), None)
                    if retry_item is None:
                        logger.info('Cooperation slot changed during retry; skipped')
                        break
                    item['inviteBtn'] = retry_item['inviteBtn']
                if self.cooperation_invite(item['inviteBtn'], name):
                    item['inviteResult'] = True
                    index = 5
                    continue
                if getattr(self, 'cooperation_recipient_unavailable', False):
                    item['skip_reason'] = '大号已有协作，可邀请列表未显示：' + name
                    logger.info(item['skip_reason'])
                    break
                logger.info("%s not found,Wait 20s,%d invitations left", name, 5 - index - 1)
                index += 1
                sleep(20) if index < 5 else sleep(0)
                # NOTE 等待过程如果出现协作邀请 将会卡住 为了防止卡住
                self.screenshot()
            # 邀请追踪一起吧,只有邀请成功才追踪
            handler = getattr(self, 'cooperation_invite_result', None)
            if handler:
                handler(item, name, item['inviteResult'])
            if item['inviteResult']:
                self.invite_success_callback(item['type'], name)
                if (self.get_config()).cooperation_only:
                    logger.info("start trace_one")
                    traced = self.trace_one(item['inviteBtn'])
                    hook = getattr(self, 'cooperation_sender_traced', None)
                    if hook:
                        if not traced:
                            raise GameStuckError('Invitation sent but sender quest could not be tracked')
                        hook(item, name)
        return ret

    def cooperation_invite(self, btn: RuleImage, name: str):
        """
            单个协作任务邀请
        @param btn:
        @param name:
        @return:
        """
        self.cooperation_recipient_unavailable = False
        if not self.ui_click(btn, stop=self.I_WQ_INVITE_ENSURE, interval=2.5, timeout=12):
            raise GameStuckError('Cannot open cooperation invitation list')

        # 选人
        self.O_WQ_INVITE_COLUMN_1.keyword = name
        self.O_WQ_INVITE_COLUMN_2.keyword = name

        find = False
        name_seen = False
        for i in range(2):
            self.wait_until_appear(self.I_WQ_INVITE_FRIEND_LIST_APPEAR, wait_time=4)
            self.screenshot()
            in_col_1 = self.ocr_appear_click(self.O_WQ_INVITE_COLUMN_1)
            in_col_2 = self.ocr_appear_click(self.O_WQ_INVITE_COLUMN_2)
            name_seen = name_seen or in_col_1 or in_col_2
            if in_col_2 or in_col_1:
                self.wait_until_appear(self.I_WQ_INVITE_SELECTED, wait_time=2)
                self.screenshot()
                find = self.appear(self.I_WQ_INVITE_SELECTED)
                if find:
                    logger.info("friend found and selected")
                    break
                # TODO OCR识别到文字 但是没有选中 尝试重新选择  (选择好友时,弹出协作邀请导致选择好友失败)
            # Inspect each list once; the old highlight template can remain
            # unmatched even after the cross-server tab has loaded.
            if i == 0:
                self.click(self.I_WQ_INVITE_DIFF_SVR, interval=1)
                sleep(1)
        # 没有找到需要邀请的人,点击取消 返回悬赏封印界面
        if not find:
            self.cooperation_recipient_unavailable = not name_seen
            self.screenshot()
            self.ui_click_until_disappear(self.I_WQ_INVITE_CANCEL, interval=1.5)
            return False
        #
        self.ui_click_until_disappear(self.I_WQ_INVITE_ENSURE, interval=1)
        return True

    def cooperation_is_realworld(self, btn: RuleImage) -> bool:
        """Inspect the quest detail without tracing or inviting it."""
        deadline = monotonic() + 15
        kind = None
        while monotonic() < deadline:
            self.screenshot()
            # Real-world details use a different heading/layout. Their portal
            # is sufficient proof even when the ordinary detail header is absent.
            if self.appear(self.I_WQ_TRACE_ONE_REALWORLD):
                kind = True
                break
            if self.appear(self.I_WQ_TRACE_ONE_CHECK_OPENED):
                if self.appear(self.I_WQ_TRACE_ONE_ENABLE) or self.appear(self.I_WQ_TRACE_ONE_DISABLE):
                    kind = False
                    break
                # The heading can appear before the quest controls finish loading.
                continue
            if self.appear(btn, interval=1.5):
                x, y, w, h = btn.roi_front
                self.device.click(x + w // 2, y - 40, control_name='cooperation_detail')
        if kind is None:
            raise GameStuckError('Cannot identify cooperation quest detail; scan incomplete')

        self.close_cooperation_detail()
        return kind

    def close_cooperation_detail(self):
        deadline = monotonic() + 10
        next_close = 0
        while monotonic() < deadline:
            self.screenshot()
            if (not self.appear(self.I_WQ_TRACE_ONE_CHECK_OPENED) and
                    not self.appear(self.I_WQ_TRACE_ONE_REALWORLD) and
                    (self.appear(self.I_TRACE_ENABLE) or self.appear(self.I_TRACE_DISABLE))):
                return
            if monotonic() >= next_close:
                # Above the wide ordinary detail and left of the narrow real-
                # world detail, without touching the SDK banner at x >= 360.
                self.device.click(300, 120, control_name='cooperation_detail_close')
                next_close = monotonic() + 1
        raise GameStuckError('Cannot return from cooperation detail to quest board')

    def get_cooperation_info(self, inspect_realworld: bool = False) -> List:
        """
            获取协作任务详情
        @return: 协作任务类型与邀请按钮
        """
        self.screenshot()
        retList = []
        for index in range(3):
            self.screenshot()
            btn = self.__getattribute__("I_WQ_INVITE_" + str(index + 1))
            if not self.appear(btn):
                continue
            reward = None
            reward_kind = None
            # Food quests also contain gold, so gold must be checked last.
            for asset, reward_type in (
                    ('JADE', CooperationType.Jade), ('DOG_FOOD', CooperationType.Food),
                    ('CAT_FOOD', CooperationType.Food), ('SUSHI', CooperationType.Sushi),
                    ('GOLD', CooperationType.Gold)):
                if self.appear(getattr(self, f'I_WQ_COOPERATION_TYPE_{asset}_{index + 1}')):
                    reward = reward_type
                    reward_kind = asset
                    break
            if reward is None:
                if inspect_realworld:
                    raise GameStuckError(f'Unknown cooperation reward in slot {index + 1}; scan incomplete')
                continue
            realworld = inspect_realworld and self.cooperation_is_realworld(btn)
            if realworld:
                # Real-world ranking is independent of ordinary food quests.
                for asset, reward_type in (('JADE', CooperationType.Jade),
                                           ('SUSHI', CooperationType.Sushi),
                                           ('GOLD', CooperationType.Gold)):
                    if self.appear(getattr(self, f'I_WQ_COOPERATION_TYPE_{asset}_{index + 1}')):
                        reward = reward_type
                        reward_kind = asset
                        break
            retList.append({'type': CooperationType.RealWorld if realworld else reward,
                            'reward_type': reward, 'reward_kind': reward_kind,
                            'slot': index + 1, 'inviteBtn': btn})
            observer = getattr(self, 'cooperation_observer', None)
            if observer:
                observer(retList)
        logger.info(f"get cooperation size {len(retList)}")
        return retList

    # 使用平均亮度检测是否一致
    def appear_highlight(self, rule_image: RuleImage):
        def compute_region_brightness(img, top_left, width, height):
            """
            计算目标区域的平均亮度 (灰度图的平均值)
            :param img: 目标图像
            :param top_left: 匹配区域的左上角坐标
            :param width: 模板宽度
            :param height: 模板高度
            :return: 区域亮度均值
            """
            # 裁剪出匹配区域
            region = img[top_left[1]:top_left[1] + height, top_left[0]:top_left[0] + width]
            # 转为灰度图
            gray_region = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            # 计算灰度均值
            return gray_region.mean()

        src = rule_image.corp(self.device.image)
        template = rule_image.image
        result = cv2.matchTemplate(src, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        brightness_src = compute_region_brightness(src, max_loc, template.shape[1], template.shape[0])
        brightness_template = compute_region_brightness(template, (0, 0), template.shape[1], template.shape[0])

        if max_val > rule_image.threshold and (brightness_src >= brightness_template * rule_image.threshold) and (
                brightness_src <= brightness_template * (2 - rule_image.threshold)):
            rule_image.roi_front[0] = max_loc[0] + rule_image.roi_back[0]
            rule_image.roi_front[1] = max_loc[1] + rule_image.roi_back[1]
            return True
        return False

    @cached_property
    def special_main(self) -> bool:
        # 特殊的庭院需要点一下，左边然后才能找到图标
        main_type = self.config.global_game.costume_config.costume_main_type
        if main_type == MainType.COSTUME_MAIN_3:
            return True
        return False

    def get_config(self):
        return self.config.wanted_quests.wanted_quests_config

    def need_invite_vip(self):
        return bool(self.get_config().invite_friend_name)

    def get_invite_vip_name(self, ctype: CooperationType):
        return self.get_config().invite_friend_name

    def invite_success_callback(self, ctype: CooperationType, name):
        """
           邀请成功回调
        @param ctype:
        @type ctype:
        @param name:
        @type name:
        """

        return True

    def process_ocr(self, txt):
        def detect_spliter(txt):
            index = txt.find('/')
            if index != -1:
                return index
            # 由于斜杠'/'经常被误识别为'7',且悬赏封印悬赏怪物总数没有与‘7’相关的数字
            reg = re.compile(r'^(\d+)([7/])(\d+)$')
            match = reg.match(txt)
            if match:
                return match.start(2)
            return -1

        index = detect_spliter(txt)
        if index < 0:
            return 0, 0, 0
        return int(txt[:index]), 1, int(txt[index + 1:])

    def txt_ocr_appear(self, ocr_item: RuleOcr, reg, img):
        res = ocr_item.ocr(img)
        regex = re.compile(reg)
        ismatch = regex.match(res)
        return ismatch is not None

    def find_wq(self, img, strict_progress=False):
        def calc_xywh(box):
            rec_x, rec_y, rec_w, rec_h = box[0, 0], box[0, 1], box[1, 0] - box[0, 0], box[2, 1] - box[0, 1]
            x = rec_x + self.O_WQ_TEXT_ALL.roi[0]
            y = rec_y + self.O_WQ_TEXT_ALL.roi[1]
            w = rec_w
            h = rec_h
            return [x, y, w, h]

        res_list = self.O_WQ_TEXT_ALL.detect_and_ocr(img)
        import re
        reg_time = re.compile(r'^([01]?[0-9]|2[0-3]):([0-5]?[0-9]):?([0-5]?[0-9])?$')
        reg_fengyin = re.compile(r'.*[封|野]印.*')
        # 由于斜杠'/'经常被误识别为'7',且悬赏封印悬赏怪物总数没有与‘7’相关的数字
        reg_progress = re.compile(r'^(\d+)([7/])(\d+)$')
        # 没有检测到斜杠，符合格式：前N位与后N位相同,表示已完成
        reg_XX = re.compile(r'^(\d+)\1$')
        # 过滤掉协或者未知悬赏等其他无用字符
        reg_other = re.compile(r'[?？协边]')
        completed_only = False
        clue_pending = False
        for index, res in enumerate(res_list):
            text = ''.join(res.ocr_text.split())
            # A mystery bounty appears as a separate question mark followed
            # by its progress.  Skipping the mark alone still selects 0/N.
            if '?' in text or '？' in text or '线索' in text or '神秘妖怪' in text:
                clue_pending = True
                self._wanted_clue_skipped = True
                completed_only = True
                continue
            if reg_fengyin.match(res.ocr_text):
                continue
            if reg_time.match(res.ocr_text):
                continue
            if reg_other.search(res.ocr_text):
                continue
            if (match := reg_progress.match(res.ocr_text)):
                if clue_pending:
                    logger.info('跳过线索悬赏：%s', res.ocr_text)
                    clue_pending = False
                    continue
                spliter_index = match.start(2)
                xywh = calc_xywh(res.box)
                self.O_WQ_TEXT_ALL.area = xywh
                cu, re, total = int(res.ocr_text[:spliter_index]), 1, int(res.ocr_text[spliter_index + 1:])
                logger.info(f'Matched: {res.ocr_text}')
                # 识别结果规范性检查
                if strict_progress and (total < 1 or cu > total):
                    logger.warning('Invalid sender quest progress; do not infer completion')
                    continue
                if not strict_progress and total > 14:
                    logger.warning("Total number of wanted quests is greater than 14")
                    total = total % 10
                if not strict_progress and cu > total:
                    logger.warning('Current number of wanted quests is greater than total number')
                    cu = cu // 10
                if cu == total:
                    # 该任务已完成，一般是悬赏任务，邀请人没有做导致的
                    completed_only = True
                    continue
                return cu, re, total, xywh
            # 例如：1414 66 1212
            if reg_XX.match(res.ocr_text):
                clue_pending = False
                continue
            # 什么都没匹配上，判断上一个识别结果如果为悬赏封印，那么认为该识别结果错误，尝试执行一次
            last_index = (index - 1) if index > 0 else 0
            if not clue_pending and reg_fengyin.match(res_list[last_index].ocr_text):
                return 0, 1, 3, calc_xywh(res_list[last_index].box)

        if completed_only:
            return -2, -2, -2, [0, 0, 0, 0]
        return -1, -1, -1, [0, 0, 0, 0]

    def is_wq_remained(self):
        # This OCR has an empty keyword, so appear() matches unrelated sidebar
        # text too (such as yokai timers and treasure chests). Require actual
        # bounty text, and confirm its absence over multiple fresh frames.
        for attempt in range(3):
            if attempt:
                sleep(0.4)
                self.screenshot()
            if self.appear(self.I_WQ_BOX) or self.appear(self.I_TREASURE_BOX_CLICK):
                return True
            results = self.O_WQ_WANTED.detect_and_ocr(self.device.image)
            if any('悬赏' in ''.join(item.ocr_text.split()) or
                   '封印' in ''.join(item.ocr_text.split()) for item in results):
                return True
        if not self.ui_page_appear(page_exploration):
            raise GameStuckError('无法确认探索地图，不能根据空侧栏判断悬赏完成')
        logger.info('No bounty labels or bounty rewards found in three sidebar frames')
        self.device.save_screenshot(genre='findjade_no_bounty_sidebar', interval=0)
        return False



if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    import re

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    # import cv2
    #
    # img = cv2.imread(r'E:\2.png')
    # img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    #
    # res = t.find_wq(img)

    t.run()
