# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import re
import time
from cached_property import cached_property
from datetime import timedelta, datetime

from module.base.timer import Timer
from module.atom.click import RuleClick
from module.atom.image_grid import ImageGrid
from module.logger import logger
from module.exception import TaskEnd

from tasks.GameUi.game_ui import GameUi
from tasks.Utils.config_enum import ShikigamiClass
from tasks.KekkaiUtilize.assets import KekkaiUtilizeAssets
from tasks.KekkaiUtilize.config import UtilizeRule, SelectFriendList
from tasks.KekkaiUtilize.utils import CardClass, target_to_card_class
from tasks.Component.ReplaceShikigami.replace_shikigami import ReplaceShikigami
from tasks.GameUi.page import page_main, page_guild
from module.base.utils import point2str
import random

""" 结界蹭卡 """


class ScriptTask(GameUi, ReplaceShikigami, KekkaiUtilizeAssets):
    FRIEND_SCAN_MAX_SWIPES = 2
    FRIEND_SCAN_MAX_FRIENDS = 10
    last_best_index = 99
    utilize_add_count = 0
    ap_max_num = 0
    jade_max_num = 0
    first_utilize = True

    # The guild template is a narrow strip on the animated courtyard icon.
    # Around the daily reset the strip can still match while clicks on its
    # edge are ignored by the game.  Keep two stable, central hit boxes as a
    # fallback instead of hammering the stale template for a full minute.
    C_MAIN_GUILD_ICON = RuleClick(
        roi_front=(558, 586, 16, 22), roi_back=(558, 586, 16, 22),
        name='kekkai_main_guild_icon')
    C_MAIN_GUILD_LABEL = RuleClick(
        roi_front=(550, 638, 30, 24), roi_back=(550, 638, 30, 24),
        name='kekkai_main_guild_label')

    def run(self):
        con = self.config.kekkai_utilize.utilize_config
        self.ui_get_current_page()
        self._goto_guild_or_retry()

        # 进入寮结界
        self.goto_realm()
        # 育成界面去蹭卡
        if con.utilize_enable:
            self.check_utilize_add()
            # KekkaiUtilize is currently dedicated to foster placement. Once
            # placement (or an existing foster) has been verified, end the
            # task immediately instead of entering max-level replacement and
            # box-harvest flows on a stale page state.
            raise TaskEnd

        # 查看育成满级
        self.check_max_lv(con.shikigami_class)
        # 检查蹭卡收获
        self.check_utilize_harvest()
        # 收体力盒子或者是经验盒子
        self.check_box_ap_or_exp(con.box_ap_enable, con.box_exp_enable, con.box_exp_waste)

        # 收取寮资金和体力
        self.recive_guild_ap_or_assets(con.harvest_guild_max_times)
        if not con.utilize_enable:
            self.set_next_run(task='KekkaiUtilize', finish=True, success=True)
        raise TaskEnd

    def _goto_guild_or_retry(self, task='KekkaiUtilize'):
        """Enter guild with bounded recovery for an unresponsive main icon."""
        if self.ui_goto(page_guild, timeout=18):
            return

        self.ui_get_current_page(skip_first_screenshot=False)
        if self.ui_current == page_main:
            for action in (self.C_MAIN_GUILD_ICON, self.C_MAIN_GUILD_LABEL):
                logger.warning(f'Guild entry stayed on main; fallback click {action.name}')
                self.click(action)
                if self.ui_wait_until_appear(page_guild, timeout=5,
                                             skip_first_screenshot=False):
                    self.ui_current = page_guild
                    logger.info('Guild entry recovered by fixed central click')
                    return

        retry_at = datetime.now() + timedelta(minutes=3)
        logger.warning(f'Guild entry unavailable; retry {task} at {retry_at}')
        self.set_next_run(task=task, target=retry_at)
        raise TaskEnd

    def recive_guild_ap_or_assets(self, max_tries: int = 3):
        for i in range(1, max_tries+1):
            self.ui_get_current_page()
            self._goto_guild_or_retry()
            # 在寮的主界面 检查是否有收取体力或者是收取寮资金
            if self.check_guild_ap_or_assets():
                logger.warning(f'第[{i}]次检查寮收获,成功')
                self.ui_goto(page_main)
                break
            else:
                logger.warning(f'第[{i}]次检查寮收获寮收获,失败')
            self.ui_goto(page_main)

    def check_utilize_add(self):
        con = self.config.kekkai_utilize.utilize_config
        while 1:
            # 无论收不收到菜，都会进入看看至少看一眼时间还剩多少
            time.sleep(0.5)
            # 进入育成界面
            self.realm_goto_grown()
            self.screenshot()

            remaining = self._verify_foster_timer()
            if remaining:
                self.set_next_run(task='KekkaiUtilize', target=datetime.now() + remaining)
                return
            # A missing OCR result is not evidence that the outgoing slot is
            # empty. Only enter friend selection from a fresh, confirmed plus.
            self.screenshot()
            if not (self.appear(self.I_RS_RECORDS_SHIKI)
                    and self.appear(self.I_UTILIZE_ADD)):
                retry_at = datetime.now() + timedelta(minutes=3)
                logger.warning('Own foster state remains unknown; defer until %s', retry_at)
                self.device.save_screenshot(genre='kekkai_foster_unconfirmed', interval=0)
                self.set_next_run(task='KekkaiUtilize', finish=True, server=False,
                                  target=retry_at)
                raise TaskEnd('Own foster state unconfirmed; retry in 3 minutes')
            if not self.grown_goto_utilize():
                logger.info('Utilize failed, exit')
                continue
            # 开始执行寄养
            if self.run_utilize(con.select_friend_list, con.shikigami_class, con.shikigami_order):
                remaining = self._verified_foster_remaining
                self.set_next_run(task='KekkaiUtilize', target=datetime.now() + remaining)
                logger.info('Foster placement completed and verified; KekkaiUtilize may end')
                return
            else:
                self.back_realm()
                if self._utilize_retry_delay:
                    logger.warning('No four-star or better foster card; retry in 3 minutes')
                    self.push_notify(content='前十位没有四星以上太鼓或斗鱼，3分钟后继续重扫')
                    # Keep this task active so lower-priority tasks cannot run
                    # before foster placement has been verified.
                    time.sleep(self._utilize_retry_delay)
                # A failed confirmation/card claim can return as far as the
                # courtyard. Normalize every retry through the normal page
                # graph instead of assuming we are still inside the realm.
                self.ui_get_current_page()
                self._goto_guild_or_retry()
                self.goto_realm()

    def _read_active_foster_timer(self):
        """Read only the rightmost outgoing (我的寄养) slot on growth pages."""
        # The middle 好友寄养 timer is an incoming friend's placement. It can
        # count down while our own slot is empty and must never imply success.
        # This is a state read, not an action: do not use the throttled
        # in_shikigami_growth() helper twice on the same screenshot.
        if not self.appear(self.I_RS_RECORDS_SHIKI) or self.appear(self.I_UTILIZE_ADD):
            return None, None
        remaining = self.O_UTILIZE_RES_TIME.ocr(self.device.image)
        if isinstance(remaining, timedelta) and remaining > timedelta(0):
            return self.O_UTILIZE_RES_TIME, remaining
        return None, None

    def _verify_foster_timer(self, confirmed_placement=False):
        """Verify outgoing foster progress across fresh frames, with a deadline.

        A missed marker/OCR sample is unknown, not an empty slot. Keep a valid
        baseline through transient misses; replace implausible baselines only
        to require another independent decreasing sample afterwards.
        """
        started = time.monotonic()
        budget = 24 if confirmed_placement else 12
        baseline_rule = baseline_remaining = baseline_at = None
        # The sample cap also bounds this loop if an injected/test clock stalls.
        for attempt in range(16):
            if attempt and time.monotonic() - started >= budget:
                break
            timer_rule, remaining = ScriptTask._read_active_foster_timer(self)
            now = time.monotonic()
            if remaining is not None:
                if baseline_remaining is not None and timer_rule is baseline_rule:
                    decrease = (baseline_remaining - remaining).total_seconds()
                    elapsed = now - baseline_at
                    if 0 < decrease <= min(30, elapsed + 2):
                        logger.info('Utilize remaining time (verified): %s -> %s',
                                    baseline_remaining, remaining)
                        return remaining
                    if decrease == 0:
                        logger.info('Own foster timer unchanged; wait for a fresh countdown')
                    else:
                        logger.warning('Own foster timer sample inconsistent: %s -> %s '
                                       '(elapsed %.1fs); require a new pair',
                                       baseline_remaining, remaining, elapsed)
                        baseline_remaining = None
                if baseline_remaining is None:
                    baseline_rule, baseline_remaining, baseline_at = timer_rule, remaining, now
                    logger.info('Utilize remaining time (first): %s', remaining)
            elif (not confirmed_placement and self.appear(self.I_RS_RECORDS_SHIKI)
                  and self.appear(self.I_UTILIZE_ADD)):
                logger.info('Own foster slot is visibly empty')
                return None
            else:
                logger.info('Own foster timer unreadable on sample %s; resample', attempt + 1)

            delay = 3 if baseline_remaining is not None else 1
            if now - started + delay >= budget:
                break
            time.sleep(delay)
            self.screenshot()

        logger.warning('Own foster countdown was not verified within %ss; state unknown', budget)
        return None

    def check_max_lv(self, shikigami_class: ShikigamiClass = ShikigamiClass.N):
        """
        在结界界面，进入式神育成，检查是否有满级的，如果有就换下一个
        退出的时候还是结界界面
        :return:
        """
        self.realm_goto_grown()
        if self.appear(self.I_RS_LEVEL_MAX):
            # 存在满级的式神
            logger.info('Exist max level shikigami and replace it')
            self.unset_shikigami_max_lv()
            self.switch_shikigami_class(shikigami_class)
            self.set_shikigami(shikigami_order=7, stop_image=self.I_RS_NO_ADD)
        else:
            logger.info('No max level shikigami')
        if self.detect_no_shikigami():
            logger.warning('There are no any shikigami grow room')
            self.switch_shikigami_class(shikigami_class)
            self.set_shikigami(shikigami_order=7, stop_image=self.I_RS_NO_ADD)

        # 回到结界界面
        while 1:
            self.screenshot()

            if self.appear(self.I_REALM_SHIN) and self.appear_multi_scale(self.I_SHI_GROWN):
                self.screenshot()
                if not self.appear(self.I_REALM_SHIN):
                    continue
                break
            if self.appear_then_click(self.I_UI_BACK_BLUE, interval=2.5):
                continue

    def check_guild_ap_or_assets(self, ap_enable: bool = True, assets_enable: bool = True) -> bool:
        """
        在寮的主界面 检查是否有收取体力或者是收取寮资金
        如果有就顺带收取
        :return:
        """
        timer_check = Timer(2)
        timer_check.start()
        click_ap = False
        while 1:
            self.screenshot()

            # 获得奖励
            if self.ui_reward_appear_click():
                timer_check.reset()
                continue

            if timer_check.reached():
                return False

            if click_ap and not self.appear(self.I_GUILD_AP) and not self.appear(self.I_UI_REWARD):
                return True

            # 关闭展开的寮活动横幅
            if self.appear_then_click(self.I_GUILD_EXPAND):
                timer_check.reset()
                continue

            # 资金收取确认
            if self.appear_then_click(self.I_GUILD_ASSETS_RECEIVE, interval=1):
                time.sleep(1)
                timer_check.reset()
                continue

            # 收资金
            if self.appear_then_click(self.I_GUILD_ASSETS, interval=1.5, threshold=0.6):
                timer_check.reset()
                continue

            # 收体力
            if self.appear_then_click(self.I_GUILD_AP, interval=1):
                # 等待1秒，看到获得奖励
                time.sleep(1)
                logger.info('appear_click guild_ap success')
                if self.ui_reward_appear_click(True):
                    logger.info('appear_click reward success')
                    click_ap = True
                    timer_check.reset()
                continue

    def goto_realm(self):
        """
        从寮的主界面进入寮结界
        :return:
        """
        while 1:
            self.screenshot()
            if self.appear(self.I_REALM_SHIN):
                break
            if self.appear_multi_scale(self.I_SHI_DEFENSE):
                break
            if self.appear_then_click(self.I_PLANT_TREE_CLOSE):
                continue
            if self.appear_then_click(self.I_GUILD_REALM, interval=1):
                continue

    def check_box_ap_or_exp(self, ap_enable: bool = True, exp_enable: bool = True, exp_waste: bool = True) -> bool:
        """
        顺路检查盒子
        :param ap_enable:
        :param exp_enable:
        :return:
        """

        # 退出到寮结界
        def _exit_to_realm():
            # 右上方关闭红色
            while 1:
                self.screenshot()
                if self.appear(self.I_REALM_SHIN):
                    break
                if self.appear_then_click(self.I_UI_BACK_RED, interval=1):
                    continue

        # 先是体力盒子
        def _check_ap_box(appear: bool = False):
            if not appear:
                return False
            # 点击盒子
            timer_ap = Timer(6)
            timer_ap.start()
            while 1:
                self.screenshot()

                if self.appear(self.I_UI_REWARD):
                    while 1:
                        self.screenshot()
                        if not self.appear(self.I_UI_REWARD):
                            break
                        if self.appear_then_click(self.I_UI_REWARD, self.C_UI_REWARD, interval=1, threshold=0.6):
                            continue
                    logger.info('Reward box')
                    break

                if self.appear_then_click(self.I_BOX_AP, interval=1):
                    continue
                if self.appear_then_click(self.I_AP_EXTRACT, interval=2):
                    continue
                if timer_ap.reached():
                    logger.warning('Extract ap box timeout')
                    break
            logger.info('Extract AP box finished')
            _exit_to_realm()

        # 经验盒子
        def _check_exp_box(appear: bool = False):
            if not appear:
                logger.info('No exp box')
                return False

            time_exp = Timer(12)
            time_exp.start()
            while 1:
                self.screenshot()
                # 如果出现结界皮肤， 表示收取好了
                if self.appear(self.I_REALM_SHIN) and not self.appear(self.I_BOX_EXP, threshold=0.6):
                    break
                # 如果出现收取确认，表明进入到了有满级的
                if self.appear(self.I_UI_CONFIRM):
                    self.screenshot()
                    if not self.appear(self.I_UI_CANCEL):
                        logger.info('No cancel button')
                        continue
                    if exp_waste:
                        check_button = self.I_UI_CONFIRM
                    else:
                        check_button = self.I_UI_CANCEL
                    while 1:
                        self.screenshot()
                        if not self.appear(check_button):
                            break
                        if self.appear_then_click(check_button, interval=1):
                            continue
                    break

                if self.appear(self.I_EXP_EXTRACT):
                    # 如果达到今日领取的最大，就不领取了
                    cur, res, totol = self.O_BOX_EXP.ocr(self.device.image)
                    if cur == res == totol == 0:
                        continue
                    if cur == totol and cur + res == totol:
                        logger.info('Exp box reach max do not collect')
                        break
                if self.appear_then_click(self.I_BOX_EXP, threshold=0.6, interval=1):
                    continue
                if self.appear_then_click(self.I_EXP_EXTRACT, interval=1):
                    continue

                if time_exp.reached():
                    logger.warning('Extract exp box timeout')
                    break
            _exit_to_realm()

        self.screenshot()
        box_ap = self.appear(self.I_BOX_AP)
        box_exp = self.appear(self.I_BOX_EXP, threshold=0.6) or self.appear(self.I_BOX_EXP_MAX, threshold=0.6)
        if ap_enable:
            _check_ap_box(box_ap)
        if exp_enable:
            _check_exp_box(box_exp)

    def check_utilize_harvest(self) -> bool:
        """
        在寮结界界面检查是否有收获
        :return: 如果没有返回False, 如果有就收菜返回True
        """
        self.screenshot()
        appear = self.appear(self.I_UTILIZE_EXP)
        if not appear:
            logger.info('No utilize harvest')
            return False

        # 收获
        self.ui_get_reward(self.I_UTILIZE_EXP)
        return True

    def realm_goto_grown(self, task='KekkaiUtilize'):
        """
        进入式神育成界面
        :return:
        """
        entry_timer = Timer(20).start()
        while 1:
            self.screenshot()

            # The shikigami-record icon can false-positive on the realm
            # overview.  The growth page has either an empty-slot add button
            # or a positive remaining-time value for an active placement.
            growth_marker = self.in_shikigami_growth()
            if growth_marker:
                growth_ready = self.appear(self.I_UTILIZE_ADD)
                if not growth_ready:
                    _, remaining_time = self._read_active_foster_timer()
                    growth_ready = remaining_time is not None
                if growth_ready:
                    break

            # A missed page marker must not trigger repeated game restarts.
            # Check before clicking, so repeated entrance matches cannot
            # bypass the local deadline via the continue below.
            if entry_timer.reached():
                retry_at = datetime.now() + timedelta(minutes=3)
                logger.warning('Growth entry not confirmed within 20s (records=%s); '
                               'defer %s until %s', growth_marker, task, retry_at)
                self.device.save_screenshot(genre='kekkai_growth_entry', interval=0)
                self.set_next_run(task=task, finish=True, server=False, target=retry_at)
                raise TaskEnd('Growth entry unconfirmed; retry in 3 minutes')

            if self.appear_then_click_multi_scale(self.I_SHI_GROWN, interval=1):
                continue
        logger.info('Enter shikigami grown')

    def grown_goto_utilize(self):
        """
        从式神育成界面到 蹭卡界面
        :return:
        """
        self.screenshot()
        if not self.appear(self.I_UTILIZE_ADD):
            logger.warning('No friend utilize entrance')
            return False

        wait_timer = Timer(30).start()
        entrance_clicks = 0
        while 1:
            self.screenshot()

            # The refreshed friend-list UI opens without a friend selected, so
            # the legacy "enter realm" button is not visible yet.  Treat the
            # server tabs as page-ready markers as well.
            if (self.appear(self.I_U_ENTER_REALM)
                    or self.appear(self.I_UTILIZE_FRIEND_GROUP)
                    or self.appear(self.I_UTILIZE_ZONES_GROUP)
                    or self.appear(self.O_UTILIZE_FRIEND_LIST_TITLE)):
                break
            if wait_timer.reached():
                logger.warning('Enter utilize timeout')
                return False
            # Open our own empty outgoing slot directly. The middle label
            # opens an incoming friend's realm, not the foster friend list.
            if entrance_clicks < 3 and self.in_shikigami_growth():
                if self.appear_then_click(self.I_UTILIZE_ADD, interval=2):
                    entrance_clicks += 1
            time.sleep(0.5)
        logger.info('Enter utilize')
        return True

    def _reset_friend_list_to_top(self) -> bool:
        """Deterministically return the friend list to its first viewport."""
        if not self.device.app_is_running():
            logger.warning('Game is not running; cannot reset friend list to top')
            return False

        # A scan moves down at most FRIEND_SCAN_MAX_SWIPES short pages. Use
        # one extra gesture in the same list area so returning to the top does
        # not depend on a single long swipe landing perfectly.
        reset_count = self.FRIEND_SCAN_MAX_SWIPES + 1
        logger.info('Reset friend list to top with %s guarded swipes', reset_count)
        for _ in range(reset_count):
            self.device.swipe((420, 260), (420, 610), duration=0.5,
                              control_name='KekkaiUtilizeFriendListResetTop')
            self.device.click_record_clear()
            time.sleep(0.6)
        self.screenshot()
        return True

    def switch_friend_list(self, friend: SelectFriendList = SelectFriendList.SAME_SERVER,
                           reset_top: bool = True) -> bool:
        """
        切换不同的服务区
        :param friend:
        :return:
        """
        logger.info('Switch friend list to %s', friend)
        if not self.device.app_is_running():
            logger.warning('Game is not running while switching friend list')
            return False
        if friend == SelectFriendList.SAME_SERVER:
            self.device.click(274, 125, control_name='UTILIZE_FRIEND_TAB')
        else:
            self.device.click(390, 125, control_name='UTILIZE_CROSS_ZONE_TAB')
        time.sleep(1.2)
        if friend == SelectFriendList.DIFFERENT_SERVER:
            time.sleep(1)
        time.sleep(0.5)
        if reset_top and not self._reset_friend_list_to_top():
            return False
        return True

    @cached_property
    def order_targets(self) -> ImageGrid:
        rule = self.config.kekkai_utilize.utilize_config.utilize_rule
        if rule == UtilizeRule.DEFAULT:
            return ImageGrid([self.I_U_TAIKO_6, self.I_U_FISH_6,
                              self.I_U_TAIKO_5, self.I_U_FISH_5,
                              self.I_U_TAIKO_4, self.I_U_FISH_4,
                              self.I_U_TAIKO_3, self.I_U_FISH_3])
        elif rule == UtilizeRule.FISH:
            return ImageGrid([self.I_U_FISH_6, self.I_U_FISH_5,
                              self.I_U_FISH_4, self.I_U_FISH_3])
        elif rule == UtilizeRule.TAIKO:
            return ImageGrid([self.I_U_TAIKO_6, self.I_U_TAIKO_5,
                              self.I_U_TAIKO_4, self.I_U_TAIKO_3])
        else:
            logger.error('Unknown utilize rule')
            raise ValueError('Unknown utilize rule')

    @cached_property
    def order_cards(self) -> list[CardClass]:
        rule = self.config.kekkai_utilize.utilize_config.utilize_rule
        result = []
        if rule == UtilizeRule.DEFAULT:
            result = [CardClass.TAIKO6, CardClass.FISH6, CardClass.TAIKO5, CardClass.FISH5,
                      CardClass.TAIKO4, CardClass.FISH4, CardClass.TAIKO3, CardClass.FISH3]
        elif rule == UtilizeRule.FISH:
            result = [CardClass.FISH6, CardClass.FISH5, CardClass.FISH4, CardClass.FISH3]
        elif rule == UtilizeRule.TAIKO:
            result = [CardClass.TAIKO6, CardClass.TAIKO5, CardClass.TAIKO4, CardClass.TAIKO3]
        else:
            logger.error('Unknown utilize rule')
            raise ValueError('Unknown utilize rule')
        return result

    def run_utilize(self, friend: SelectFriendList = SelectFriendList.SAME_SERVER,
                    shikigami_class: ShikigamiClass = ShikigamiClass.N,
                    shikigami_order: int = 7):
        """
        执行寄养
        :param shikigami_class:
        :param friend:
        :param rule:
        :return:
        """
        logger.hr('Start utilize')
        self.first_utilize = False
        self._utilize_retry_delay = 0
        self._verified_foster_remaining = None

        # 本区优先、跨区其次，每区只检查顶部约 15 位好友。
        # 一旦找到六星太鼓/斗鱼，保留选中状态并立即进入寄养。
        # Current six-hour yields. Rank 0/1/2 means six/five/four star.
        resource_presets = {
            '斗鱼': [126, 101, 84],
            '太鼓': [76, 67, 59],
        }

        def resource_index(card_type, value):
            for index, threshold in enumerate(resource_presets[card_type]):
                if value >= threshold:
                    return index
            return 99

        selection_retry = 0
        while True:
            candidates = {}
            perfect_selection = None
            for friend_list in (SelectFriendList.SAME_SERVER,
                                SelectFriendList.DIFFERENT_SERVER):
                if not self.switch_friend_list(friend_list):
                    return False
                self.ap_max_num, self.jade_max_num = 0, 0
                perfect_card = self._current_select_best()
                candidates[friend_list] = (self.ap_max_num, self.jade_max_num)
                if perfect_card:
                    perfect_selection = (perfect_card[0], perfect_card[1], friend_list)
                    logger.info('Six-star card found; stop scanning: %s @ %s (%s)',
                                perfect_card[0], perfect_card[1], friend_list)
                    break

            if perfect_selection:
                # _current_select_best leaves the six-star card selected.
                break

            choices = []
            for friend_list, (fish_value, taiko_value) in candidates.items():
                if fish_value > 0:
                    choices.append(('斗鱼', fish_value, friend_list,
                                    resource_index('斗鱼', fish_value)))
                if taiko_value > 0:
                    choices.append(('太鼓', taiko_value, friend_list,
                                    resource_index('太鼓', taiko_value)))
            choices = [item for item in choices if item[3] <= 2]
            if not choices:
                logger.warning('No four-star or better Taiko/Fish in top ten friends')
                self._utilize_retry_delay = 180
                return False

            # 档位越小越好；同档位优先太鼓。低于预设时按相对收益比较。
            def choice_key(item):
                card_type, value, _, index = item
                if index == 99:
                    base = resource_presets[card_type][0]
                    return index, -(value / base), 0 if card_type == '太鼓' else 1
                return index, 0, 0 if card_type == '太鼓' else 1, -value

            best_type, best_value, best_list, _ = min(choices, key=choice_key)
            logger.info('Best card across both lists: %s @ %s (%s)',
                        best_type, best_value, best_list)
            if not self.switch_friend_list(best_list):
                return False
            if self._current_select_best(best_type, best_value, selected_card=True):
                break

            # 回选期间坑位被抢时，立即重扫并尝试下一张。
            selection_retry += 1
            if selection_retry >= 10:
                logger.warning('Card selection failed after %s rescans', selection_retry)
                return False
            logger.warning('Selected card disappeared; rescan both lists (%s/10)',
                           selection_retry)
            time.sleep(1)

        # 找到卡,重置次数
        self.utilize_add_count = 0
        logger.info('开始执行进入结界蹭卡流程')
        self.screenshot()
        # The refreshed button shifted three pixels left of the legacy ROI.
        self.device.click(879, 565, control_name='UTILIZE_ENTER_REALM')
        time.sleep(1)
        wait_timer = Timer(60)
        wait_timer.start()
        direct_selection = False
        refreshed_path_started = False
        foster_entrance_clicked = False
        while 1:
            self.screenshot()
            if foster_entrance_clicked and self.in_shikigami_growth():
                logger.info('Friend foster selection page appeared after clicking 寄')
                direct_selection = True
                break
            if self.in_foster_selection():
                # The friend-list transition can briefly retain the records
                # icon from the page behind it.  Require it to remain visible
                # after the transition settles before treating this as the
                # actual shikigami-selection page.
                time.sleep(1)
                self.screenshot()
                if self.in_foster_selection():
                    logger.info('Friend foster shikigami selection page appeared')
                    direct_selection = True
                    break
            # The round 寄 marker moves vertically with the realm skin. Its
            # template search area covers both old and current layouts.
            if self.appear(self.I_CHECK_FRIEND_REALM_2, interval=1.5):
                x, y = self.I_CHECK_FRIEND_REALM_2.front_center()
                display_id = self.device.tap_active_app_display(x, y)
                self.device.click_record_add(self.I_CHECK_FRIEND_REALM_2.name)
                logger.info('Click friend foster entrance at (%s, %s) on display %s',
                            x, y, display_id)
                foster_entrance_clicked = True
                time.sleep(2)
                continue
            # Current skins first land on the friend's growth page. Open its
            # 3D overview through the vertical 好友寄养 label.
            if (not refreshed_path_started and self.in_shikigami_growth()
                    and self.appear(self.I_U_ADD_2)):
                display_id = self.device.tap_active_app_display(913, 90)
                self.device.click_record_add('FRIEND_FOSTER_LABEL')
                logger.info('Open refreshed friend realm on display %s', display_id)
                refreshed_path_started = True
                time.sleep(2)
                continue
            _, friend_remaining = self._read_active_foster_timer()
            if (self.in_shikigami_growth()
                    and isinstance(friend_remaining, timedelta)
                    and friend_remaining > timedelta(0)):
                logger.warning('Friend foster position occupied: %s', friend_remaining)
                return False
            if self.appear(self.I_U_ADD_1) or self.appear(self.I_U_ADD_2):
                logger.info('Appear legacy friend foster position')
                break
            if self.appear(self.I_CHECK_FRIEND_REALM_1):
                self.wait_until_stable(self.I_CHECK_FRIEND_REALM_1)
                logger.info('Appear enter friend realm button')
                break
            if self.appear(self.I_CHECK_FRIEND_REALM_3):
                self.wait_until_stable(self.I_CHECK_FRIEND_REALM_3)
                logger.info('Appear enter friend realm button')
                break
            if self.appear_then_click(self.I_U_ENTER_REALM, interval=2.5):
                time.sleep(0.5)
                continue
            if wait_timer.reached():
                self.save_image(wait_time=0, push_flag=False, content='进入好友结界超时', image_type='png')
                logger.warning('Appear friend realm timeout')
                return False
        logger.info('Enter friend realm')

        # 判断好友的有两个位置还是一个坑位
        stop_image = None
        self.screenshot()
        if direct_selection:
            logger.info('Directly entered shikigami selection')
            stop_image = self.I_RS_RECORDS_SHIKI
        elif self.appear(self.I_U_ADD_1):  # 右侧第一个有（无论左侧有没有）
            logger.info('Right side has one')
            stop_image = self.I_U_ADD_1
        elif self.appear(self.I_U_ADD_2) and not self.appear(self.I_U_ADD_1):  # 右侧第二个有 但是最左边的没有，这表示只留有一个坑位
            logger.info('Right side has two')
            stop_image = self.I_U_ADD_2
        if not stop_image:
            # 没有坑位可能是其他人的手速太快了抢占了
            self.save_image(content='没有坑位了', wait_time=0, push_flag=False, image_type='png')
            logger.warning('没有坑位可能是其他人的手速太快了抢占了')
            return False
        # 保持默认“全部”分类，直接放列表中的第一个式神。结界寄养不再
        # 切换到 N 分类，也不使用配置中的旧序号。
        shikigami_order = 1
        # 上式神。弹窗消失不等于寄养成功；只有右上角倒计时连续
        # 两次递减，才允许本任务结束并让调度器执行其他任务。
        if not self.set_shikigami(shikigami_order, stop_image,
                                  require_confirmation=True):
            return False
        # The confirmation closes while we are still on the friend's
        # shikigami-selection page.  The active foster timer belongs to our
        # own growth page, so it cannot be verified here.  Leave the friend's
        # realm first, then return through the normal realm navigation before
        # checking the decreasing timer.
        logger.info('Foster confirmation closed; return to own realm for verification')
        self.back_realm()
        self.ui_get_current_page()
        self._goto_guild_or_retry()
        self.goto_realm()
        self.realm_goto_grown()
        self.screenshot()
        remaining = self._verify_foster_timer(confirmed_placement=True)
        if not remaining:
            logger.warning('Foster confirmation was not followed by a valid active timer')
            return False
        self._verified_foster_remaining = remaining
        return True

    def _select_optimal_resource_card(self):
        """整合后的智能选卡主逻辑（无嵌套函数版）"""
        # 类常量声明（需在类中定义）
        RESOURCE_PRESETS = {
            '斗鱼': [151, 143, 134, 126, 101, 84],
            '太鼓': [76,  76,  67,  67,  59,  50]
        }
        MAX_INDEX = 99

        def get_resource_index(resource_name, current_value, preset_values):
            """获取资源匹配的档位索引"""
            for idx, val in enumerate(preset_values):
                if current_value >= val:
                    logger.info(f'📊 {resource_name}区间匹配: {current_value} ≥ {val} (档位{idx})')
                    return idx
            logger.warning(f'⚠️ {resource_name}值[{current_value}]低于所有预设')
            return MAX_INDEX

        while True:
            self.screenshot()

            # 第一阶段：初始记录获取
            if self.ap_max_num == 0 and self.jade_max_num == 0:
                logger.hr('第一阶段：初始记录获取', 2)
                if self._current_select_best():
                    logger.info(f'✅ 完美结界卡确认成功，重置状态')
                    self.ap_max_num, self.jade_max_num = 0, 0
                    return True
                logger.info(f'📝 记录最佳值 | 斗鱼:{self.ap_max_num} 太鼓:{self.jade_max_num}')
                return False

            logger.hr('第二阶段：资源优先级判断', 2)
            # 获取双资源档位
            ap_index = get_resource_index('斗鱼', self.ap_max_num, RESOURCE_PRESETS['斗鱼'])
            jade_index = get_resource_index('太鼓', self.jade_max_num, RESOURCE_PRESETS['太鼓'])

            # 双资源超限处理
            if ap_index == MAX_INDEX and jade_index == MAX_INDEX:
                logger.warning('🔄 斗鱼和太鼓均低于预设，重置初始记录')
                self.ap_max_num, self.jade_max_num = 0, 0
                return False

            # 决策优先级
            res_type, target = ('斗鱼', self.ap_max_num) if ap_index <= jade_index else ('太鼓', self.jade_max_num)
            logger.info(f'⚖️ 选择{res_type}卡 | 目标: {target}')

            # 第三阶段：执行选卡操作
            logger.hr('第三阶段：执行选卡操作', 2)
            if self._current_select_best(res_type, target, selected_card=True):
                logger.info(f'✅ {res_type}卡确认成功，重置状态')
                self.ap_max_num, self.jade_max_num = 0, 0
                return True
            else:
                logger.warning(f'❌ {res_type}卡确认失败，重置状态')
                self.ap_max_num, self.jade_max_num = 0, 0
                return False

    def _current_select_best(self, best_card_type=None, best_card_num=0, selected_card=False):
        """结界卡选择核心逻辑（集成版）
        功能：滑动屏幕寻找最优资源卡，支持两种模式：
        - 探索模式：记录当前遇到的最佳结界卡数值
        - 确认模式：根据给定条件选择指定类型结界卡

        :param best_card_type: 目标卡类型('太鼓'/'斗鱼')
        :param best_card_num:  要求的最低数值
        :param selected_card:  是否处于确认选择模式
        :return: 找到符合条件返回True，否则None
        """
        # ============== 配置常量 ==============#
        RESOURCE_CONFIG = {
            '斗鱼': {'max': 151, 'record_attr': 'ap_max_num'},
            '太鼓': {'max': 76, 'record_attr': 'jade_max_num'}
        }
        MAX_SWIPES = self.FRIEND_SCAN_MAX_SWIPES
        CONSEC_MISS = 3  # 允许连续无卡次数
        TIMEOUT = 120  # 操作超时(秒)

        # ============== 初始化阶段 ==============#
        logger.info(f'启动{"探索模式" if not selected_card else f"确认模式 | 目标: {best_card_type} @ {best_card_num}"}')
        timer = Timer(TIMEOUT).start()
        miss_count = 0  # 连续无卡计数器
        checked_friends = 0
        max_friends = self.FRIEND_SCAN_MAX_FRIENDS

        # ============== 主滑动循环 ==============#
        for swipe_count in range(MAX_SWIPES + 1):
            # 超时检测
            if timer.reached():
                logger.warning('⏰ 操作超时，终止流程')
                return None

            # ------ 步骤1: 截图识别结界卡 ------#
            self.screenshot()
            cards = self.order_targets.find_everyone(self.device.image)

            # Different star templates can match the same friend's card at
            # nearly identical coordinates.  Collapse those matches into one
            # friend row and keep only the strongest match, so every friend is
            # clicked once.
            if cards:
                friend_rows = []
                for card in cards:
                    center_y = card[2][1] + card[2][3] // 2
                    for row in friend_rows:
                        if abs(center_y - row['center_y']) <= 55:
                            if card[1] > row['card'][1]:
                                row['card'] = card
                                row['center_y'] = center_y
                            break
                    else:
                        friend_rows.append({'center_y': center_y, 'card': card})
                cards = [row['card'] for row in friend_rows]

            # 处理无卡情况
            if not cards:
                # Once this list has yielded a usable card, an empty viewport
                # means we have left the useful top section.  Do not keep
                # scrolling toward the bottom; let the caller compare the best
                # card already recorded for this list.
                if (not selected_card
                        and (self.ap_max_num > 0 or self.jade_max_num > 0)):
                    logger.info('Top friend scan ended after the first empty viewport')
                    return None
                miss_count += 1
                logger.info(f'第{swipe_count}次滑动 | 未检测到结界卡' if swipe_count > 0 else '初始界面 | 未检测到结界卡')
                # 连续无卡超过阈值则终止
                if miss_count > CONSEC_MISS:
                    logger.warning(f'⚠️ 连续{miss_count}次 | 未检测到结界卡, 终止流程')
                    return None
                if swipe_count >= MAX_SWIPES:
                    break
                # 执行滑动操作
                if not self.perform_swipe_action():
                    return None
                continue

            miss_count = 0  # 重置无卡计数器

            # ------ 步骤2: 处理识别到的结界卡 ------
            cards_list = [target for target, _, _ in cards]
            logger.info((f'第{swipe_count}次滑动' if swipe_count > 0 else '初始界面') + f' | 检测到结界卡：{cards_list}')

            # 遍历所有结界卡（已按位置排序）
            for target, _, area in cards:
                if checked_friends >= max_friends:
                    logger.info('Reached top friend limit: %s', max_friends)
                    return None
                checked_friends += 1
                logger.info('Check top friend %s/%s', checked_friends, max_friends)
                # 设置点击区域并获取结界卡详情
                self.C_SELECT_CARD.roi_front = area
                self.click(self.C_SELECT_CARD)
                time.sleep(2)  # 等待结界卡详情加载

                # 解析结界卡类型和数值
                card_type, card_value = self.check_card_num()

                # 跳过无效结界卡（类型未知或数值异常）
                if card_type == 'unknown' or card_value <= 0 or card_type not in RESOURCE_CONFIG:
                    logger.info(f'⏭️ 跳过无效卡: {card_type}@{card_value}')
                    continue

                # ====== 模式分支处理 ======#
                record_attr = RESOURCE_CONFIG[card_type]['record_attr']
                current_record = getattr(self, record_attr, 0)
                logger.info(f'🔍 识别卡片: {card_type} | 当前值: {card_value}, 最优值: {current_record}')

                # 更新最佳记录
                if card_value > current_record:
                    logger.info(f'📈 更新记录: {card_type} | {current_record} → {card_value}')
                    setattr(self, record_attr, card_value)

                if selected_card:  # 确认选择模式
                    # 检查是否符合选择条件
                    if (card_type == best_card_type) and (card_value >= best_card_num):
                        logger.info(f'🎉 确认蹭卡: {card_type} | 当前值: {card_value} ≥ 目标值: {best_card_num}')
                        self.save_image(push_flag=False, wait_time=0, content=f'🎉 确认蹭卡（{card_type}: {card_value}）')
                        return True
                    # The original card may be claimed while switching tabs.
                    # Accept an alternative card of the same or better tier
                    # instead of discarding the whole scan.
                    fallback_thresholds = {
                        '斗鱼': [126, 101, 84],
                        '太鼓': [76, 67, 59],
                    }

                    def fallback_rank(kind, value):
                        for rank, threshold in enumerate(fallback_thresholds[kind], start=1):
                            if value >= threshold:
                                return rank
                        return 99

                    target_rank = fallback_rank(best_card_type, best_card_num)
                    current_rank = fallback_rank(card_type, card_value)
                    if current_rank <= target_rank:
                        logger.info('🎉 原卡已变化，改选同档或更高档: %s@%s (目标 %s@%s)',
                                    card_type, card_value, best_card_type, best_card_num)
                        self.save_image(push_flag=False, wait_time=0,
                                        content=f'🎉 改选蹭卡（{card_type}: {card_value}）')
                        return True
                else:  # 探索记录模式
                    # 星级必须由模板判断；太鼓五星和六星的 OCR 值都可能是 76。
                    if target in (self.I_U_FISH_6, self.I_U_TAIKO_6):
                        message = f'🎉 完美蹭卡 | {card_type}: {card_value}'
                        logger.info(message)
                        self.save_image(push_flag=False, wait_time=0, content=message)
                        return card_type, card_value

            # ------ 步骤3: 滑动到下一屏 ------#
            if swipe_count >= MAX_SWIPES:
                break
            if not self.perform_swipe_action():
                return None

        # ============== 终止处理 ==============#
        logger.warning(f'⚠️ 已达到最大滑动次数{MAX_SWIPES}, 终止流程')
        return None

    def perform_swipe_action(self):
        """统一滑动操作"""
        if not self.device.app_is_running():
            logger.warning('Game is not running; cancel friend-list swipe')
            return False
        duration = 0.6
        safe_pos_x = random.randint(340, 500)
        safe_pos_y = random.randint(470, 520)
        p1 = (safe_pos_x, safe_pos_y)
        p2 = (safe_pos_x, safe_pos_y - 180)
        logger.info('Swipe %s -> %s, %sS ' % (point2str(*p1), point2str(*p2), duration))
        self.device.swipe(p1, p2, duration=duration,
                          control_name='KekkaiUtilizeFriendListSwipe')

        # self.swipe(self.S_U_UP, duration=1, wait_up_time=1)
        self.device.click_record_clear()
        time.sleep(1.2)
        return True

    def check_card_num(self) -> tuple[str, int]:
        """优化版数值提取方法，返回结界卡类型及对应数值"""
        self.screenshot()
        # OCR识别
        raw_text = self.O_CARD_NUM.ocr(self.device.image)
        # logger.info(f'OCR原始结果: {raw_text}')

        # 判断结界卡类型
        if any(c in raw_text for c in ['体', 'カ', '力']):
            card_type = '斗鱼'
        elif any(c in raw_text for c in ['勾', '玉']):
            card_type = '太鼓'
        else:
            logger.warning(f'结界卡类型识别失败，原始内容: {raw_text}')
            # self.push_notify(content=f'结界卡类型识别失败: {raw_text}')
            return 'unknown', 0  # 未知类型返回0

        # 提取纯数字部分（兼容带+号的情况，如+100）
        cleaned = re.sub(r'[^\d+]', '', raw_text)  # 保留数字和加号
        match = re.search(r'\d+', cleaned)  # 匹配连续数字

        try:
            value = int(match.group()) if match else 0
        except ValueError:
            logger.warning(f'数值转换异常，清理后文本: {cleaned}')
            value = 0

        if value <= 0:
            self.push_notify(content=f'数值异常: {raw_text} -> 解析值: {value}')
            return card_type, 0

        # logger.info(f'识别成功: 卡类型: {card_type}, 数值: {value}')
        return card_type, value

    def back_guild(self):
        """
        回到寮的界面
        :return:
        """
        while 1:
            self.screenshot()

            if self.appear(self.I_GUILD_INFO):
                break
            if self.appear(self.I_GUILD_REALM):
                break
            if self.appear_then_click(self.I_PLANT_TREE_CLOSE):
                continue

            if self.appear_then_click(self.I_UI_BACK_RED, interval=1):
                continue
            if self.appear_then_click(self.I_UI_BACK_BLUE, interval=1):
                continue
            if self.appear_then_click(self.I_UI_BACK_YELLOW, interval=1):
                continue

    def back_realm(self):
        # 回到寮结界
        while 1:
            self.screenshot()
            if self.appear(self.I_REALM_SHIN):
                break
            if self.appear_multi_scale(self.I_SHI_DEFENSE):
                break
            if self.appear_then_click(self.I_UI_BACK_RED, interval=1):
                continue
            if self.appear_then_click(self.I_UI_BACK_BLUE, interval=1):
                continue


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    c = Config('switch')
    d = Device(c)
    t = ScriptTask(c, d)
    for i in range(10):
        t.perform_swipe_action()
    t.recive_guild_ap_or_assets()
    # t.check_utilize_add()
    # t.check_card_num('勾玉', 67)
    # t.screenshot()
    # print(t.appear(t.I_BOX_EXP, threshold=0.6))
    # print(t.appear(t.I_BOX_EXP_MAX, threshold=0.6))
