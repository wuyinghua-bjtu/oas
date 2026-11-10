from tasks.WantedQuests.config import CooperationType, WantedQuestsConfig
from tasks.GameUi.page import page_main, page_exploration
from module.exception import GameStuckError
from module.logger import logger
from time import monotonic, sleep
import re
from tasks.WantedQuests.explore import ExploreWantedBoss
from tasks.Orochi.assets import OrochiAssets
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from module.atom.image import RuleImage
from module.atom.click import RuleClick

class SenderBattleFailed(GameStuckError):
    """A positively identified sender battle loss; preserve pending work."""

SENDER_SOUL_BONUS = RuleImage(roi_front=(775,222,255,30), roi_back=(765,212,275,50),
    method='Template matching', threshold=0.85, file='./tasks/FindJade/res/sender_soul_bonus.png')
SENDER_SOUL_BONUS_CLOSE = RuleClick((1115,135,25,25),(1115,135,25,25),name='sender_soul_bonus_close')
COOPERATION_RESOURCE_PANEL = RuleImage(roi_front=(465,45,305,60), roi_back=(455,35,325,80),
    method='Template matching', threshold=0.85, file='./tasks/FindJade/res/cooperation_resource_panel.png')
COOPERATION_RESOURCE_CLOSE = RuleClick((1175,70,20,20),(1175,70,20,20),name='findjade_resource_close')
SENDER_QUEST_REWARD = RuleImage(roi_front=(520,210,240,55),roi_back=(480,180,330,105),
    method='Template matching',threshold=0.85,file='./tasks/FindJade/res/sender_quest_reward.png')
SENDER_QUEST_REWARD_CLOSE = RuleClick((620,500,40,20),(620,500,40,20),name='sender_quest_reward_close')


def close_sender_soul_bonus(self):
    if not self.appear(SENDER_SOUL_BONUS):
        return False
    self.click(SENDER_SOUL_BONUS_CLOSE)
    logger.info('FindJade closed soul bonus announcement')
    return True


def clear_sender_settlement(self):
    if self.appear(SENDER_QUEST_REWARD):
        self.click(SENDER_QUEST_REWARD_CLOSE,interval=1)
        return True
    if self.close_sender_soul_bonus():
        return True
    for reward in (self.I_REWARD, self.I_REWARD_GOLD):
        if self.appear_then_click(reward, action=self.C_REWARD_1, interval=1.5):
            return True
    return False


def need_invite_vip(self):
    return True


def get_invite_vip_name(self, ctype: CooperationType):
    if not self.fade_conf:
        return ""
    return self.fade_conf.get_invite_name(ctype)


def next_run(self):
    pass


def invite_success_callback(self, ctype: CooperationType, name: str):
    if not self.fade_conf:
        return
    self.fade_conf.update_invite_history(ctype, name)
    if self.config.model.find_jade is not self.fade_conf:
        self.config.model.find_jade = self.fade_conf
    self.config.save()


def get_config(self):
    config=WantedQuestsConfig()
    config.invite_friend_name="default"
    config.cooperation_only=True
    config.cooperation_type=self.fade_conf.get_cooperation_type_mask()
    return config


def get_cooperation_info(self):
    # Real-world quests are recorded only, regardless of their reward.
    items = self.read_cooperation_info(inspect_realworld=True)
    return [item for item in items if item['type'] != CooperationType.RealWorld]


def cooperation_observer(self, items):
    self.cooperation_report.observe(self.support_account, items)


def cooperation_invite_result(self, item, name, success):
    self.cooperation_report.invitation(self.support_account, item, name, success)


def cooperation_sender_traced(self, item, name):
    self.cooperation_report.sender_traced(self.support_account, item, name)


def close_cooperation_detail(self):
    """Close only a confirmed detail; never repeatedly tap the courtyard."""
    deadline = monotonic() + 15
    board_frames = 0
    main_frames = 0
    recovered = False
    resource_closed = False
    next_close = 0
    while monotonic() < deadline:
        self.screenshot()
        if self.appear(COOPERATION_RESOURCE_PANEL):
            if resource_closed:
                # Wait for the single close action to settle, never repeat it.
                continue
            logger.warning('FindJade resource panel interrupted quest inspection; close known panel once')
            self.click(COOPERATION_RESOURCE_CLOSE)
            resource_closed = True
            board_frames = main_frames = 0
            continue
        detail = (self.appear(self.I_WQ_TRACE_ONE_CHECK_OPENED) or
                  self.appear(self.I_WQ_TRACE_ONE_REALWORLD))
        if detail:
            board_frames = main_frames = 0
            if monotonic() >= next_close:
                if getattr(self,'black_gold_skin',False):
                    self.click(self.I_WQ_TRACE_ONE_CHECK_OPENED)
                    next_close=monotonic()+1.5
                    continue
                # Left of both detail layouts, below login/download overlays.
                # The real-world portal occupies x=850..1030,y=470..650.
                self.device.click(100,620,control_name='findjade_detail_close')
                next_close = monotonic() + 1.5
            continue
        if self.appear(self.I_TRACE_ENABLE) or self.appear(self.I_TRACE_DISABLE):
            board_frames += 1
            main_frames = 0
            if board_frames >= 2:
                return
            continue
        board_frames = 0
        if self.ui_page_appear(page_main):
            main_frames += 1
            if main_frames >= 2:
                if recovered:
                    break
                logger.warning('FindJade detail returned to courtyard; reopen quest board once')
                recovered = True
                if not self.open_cooperation_board():
                    break
                main_frames = 0
        else:
            main_frames = 0
    raise GameStuckError('Cannot confirm quest board after detail; stopped without blind closing clicks')


def enter_sender_exploration(self):
    """FindJade-only navigation for changing courtyard artwork."""
    deadline = monotonic() + 25
    confirmed_frames = 0
    entered_at = None
    while monotonic() < deadline:
        self.screenshot()
        if self.clear_sender_settlement():
            continue
        if self.sender_exploration_visible():
            confirmed_frames += 1
            if confirmed_frames >= 2:
                self.ui_current = page_exploration
                return
            continue
        confirmed_frames = 0
        # The SDK welcome toast hides the top ticket marker, and the map
        # controls load after its back arrow. Do not back out mid-transition.
        if entered_at is not None and monotonic() - entered_at < 6:
            continue
        if not self.ui_page_appear(page_main):
            self.appear_then_click(self.I_BACK_YOLLOW, interval=2)
            continue
        if self.appear_then_click(self.I_MAIN_GOTO_EXPLORATION, interval=2):
            entered_at = monotonic()
            continue
        if self.ocr_appear_click(self.O_HOME_EXPLORE, interval=2):
            entered_at = monotonic()
            logger.info('FindJade clicked exploration; wait for map confirmation')
    raise GameStuckError('Cannot enter exploration for sender cooperation within 25s')


def sender_exploration_visible(self):
    bottom = (self.appear(self.I_EXPLORATION_GOTO_SOUL_ZONE) and
              self.appear(self.I_EXPLORATION_GOTO_AWAKE_ZONE))
    return bottom and (self.appear(self.I_BACK_YOLLOW) or self.appear(self.I_CHECK_EXPLORATION))


def ui_page_appear(self, page, skip_first_screenshot=True, interval=None):
    # Battle helpers also use GameUi navigation when returning to the map.
    if page is page_exploration:
        self.maybe_screenshot(skip_first_screenshot)
        return self.sender_exploration_visible()
    return self.original_ui_page_appear(page,skip_first_screenshot,interval)


def wait_until_stable(self, target, *args, **kwargs):
    if target is self.I_CHECK_EXPLORATION:
        return self.enter_sender_exploration()
    return self.original_wait_until_stable(target,*args,**kwargs)


def is_wq_remained(self):
    # The shared battle runner can return while a page transition is ongoing.
    # Never infer completion from an empty sidebar on a different page.
    self.enter_sender_exploration()
    return self.read_wq_remained()


def sender_challenge_tickets(self):
    text = ''.join((self.O_WQ_NUMBER.ocr(self.device.image) or '').split())
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 0


def sender_tracker_visible(self):
    # The tracked-bounty list only renders inside a chapter map, so a missing
    # sidebar must not be read as "no quest left".
    self.screenshot()
    if self.appear(self.I_WQ_BOX) or self.appear(self.I_TREASURE_BOX_CLICK):
        return True
    for result in self.O_WQ_TEXT_ALL.detect_and_ocr(self.device.image):
        text = ''.join(result.ocr_text.split())
        if re.fullmatch(r'\d+/\d+', text) or re.fullmatch(r'\d{4}', text):
            return True
    return False


def finish_sender_cooperation(self):
    self.ui_click_until_disappear(self.I_UI_BACK_RED)
    self.enter_sender_exploration()
    self.unwanted_boss_name_list = []
    self.want_strategy_excluding = []
    for attempt in range(6):
        if self.sender_tracker_visible():
            if not self.complete_traced_quests(strict=True):
                raise GameStuckError('Sender cooperation quests are still unfinished')
            return
        logger.info('悬赏追踪列表不在当前页面，改用悬赏板复核进度')
        if not self.open_cooperation_board():
            raise GameStuckError('Cannot reopen quest board to verify sender cooperation')
        items = self.read_cooperation_info()
        outstanding = [item for item in items if item.get('already_shared')
                       and not item.get('completed')
                       and item['type'] != CooperationType.RealWorld]
        if not outstanding:
            logger.info('悬赏板确认小号协作已无未完成项，结束等待')
            self.ui_click_until_disappear(self.I_UI_BACK_RED)
            return
        routes = self.sender_routes(self.device.image, self.sender_challenge_tickets())
        if not routes:
            raise GameStuckError('No available sender route to finish cooperation')
        _, destination, per_battle, button, kind = routes[0]
        batch = 1 if kind in ('秘闻', '探索') else min(per_battle, 6)
        logger.info('FindJade board-driven follow-up: %s %s x%s', kind, destination, batch)
        {'挑战': self.challenge, '探索': self.explore, '秘闻': self.secret,
         '御魂': self.sender_soul}[kind](button, batch)
        self.enter_sender_exploration()
    raise GameStuckError('Cannot confirm sender cooperation after board-driven retries')


def find_wq(self, image, strict_progress=False):
    if not strict_progress:
        return self.read_wanted_progress(image, strict_progress=False)
    completed = False
    for result in self.O_WQ_TEXT_ALL.detect_and_ocr(image):
        text = ''.join(result.ocr_text.split()).replace('／', '/')
        progress = None
        if text.isdigit() and len(text) % 2 == 0 and text[:len(text)//2] == text[len(text)//2:]:
            progress = (int(text[:len(text)//2]), int(text[len(text)//2:]))
        else:
            match = re.fullmatch(r'(\d+)[/7](\d+)', text)
            if match:
                progress = (int(match.group(1)), int(match.group(2)))
        if progress is None:
            continue
        current, total = progress
        if not (1 <= total <= 999 and 0 <= current <= total):
            continue
        if current == total:
            completed = True
            continue
        box = result.box
        roi = self.O_WQ_TEXT_ALL.roi
        area = [roi[0]+box[0][0], roi[1]+box[0][1],
                box[1][0]-box[0][0], box[2][1]-box[0][1]]
        previous = getattr(self, 'sender_last_route_result', None)
        if previous is not None:
            old_current, old_total, old_y, old_route = previous
            if old_total == total and abs(old_y - area[1]) <= 25:
                if current <= old_current:
                    self.sender_excluded_routes.add(old_route)
                    logger.warning('悬赏进度未增加，排除路线 %s', old_route)
                else:
                    logger.info('悬赏进度已增加：%s/%s -> %s/%s', old_current, old_total, current, total)
            self.sender_last_route_result = None
        self.sender_selected_progress = (current, total, area[1])
        logger.info('FindJade sender progress: %s/%s', current, total)
        return current, 1, total, area
    # A completed counter must not fall through to the unrelated navigation
    # labels (e.g. realm raid) and fabricate another 0/3 bounty.
    return (-2,-2,-2,[0,0,0,0]) if completed else (-1,-1,-1,[0,0,0,0])


def sender_routes(self, image, challenge_tickets):
    """Only consider destinations with an actual enabled Go button."""
    settings = self.config.model.wanted_quests.wanted_quests_config
    priority = settings.battle_priority.replace(' ', '').split('>')
    layers = ['壹','贰','叁','肆','伍','陆','柒','捌','玖','拾','番外']
    limit = settings.layer_limit.value
    excluded_layers = layers[layers.index(limit):] if limit in layers else []
    routes = []
    for number in range(1,5):
        button = getattr(self, f'I_GOTO_{number}')
        if not self.appear(button):
            logger.info('FindJade skipped route %s: Go button unavailable', number)
            continue
        kind = ''.join(getattr(self,f'O_WQ_TYPE_{number}').ocr(image).split())
        # A shikigami-fragment dungeon completes the bounty in one deterministic
        # run and does not spend challenge tickets, so it always outranks the
        # configured group order. Keep the challenge executor for entry.
        fragment = kind.startswith('式神')
        if fragment:
            kind = '挑战'
        if kind not in ('挑战','探索','秘闻','御魂') or kind not in priority:
            continue
        if kind == '挑战' and not fragment and challenge_tickets <= 0:
            continue
        text = getattr(self,f'O_WQ_INFO_{number}').ocr(image)
        match = re.fullmatch(r'(.+?)[(（]数量[:：]\s*(\d+)[)）]?', text.strip())
        if not match or int(match.group(2)) < 1:
            continue
        destination = match.group(1)
        if kind == '秘闻' and any(destination.endswith(layer) for layer in excluded_layers):
            continue
        order = -1 if fragment else priority.index(kind)
        route = (order, destination, int(match.group(2)),button,kind)
        if (kind,destination) not in self.sender_excluded_routes:
            routes.append(route)
            if fragment:
                logger.info('FindJade fragment dungeon takes first priority: %s', destination)
    def route_key(route):
        _, destination, _, _, kind = route
        chapter = 999
        if kind == '探索':
            match = re.fullmatch(r'第([一二三四五六七八九十]+)章', destination)
            if match:
                text = match.group(1)
                digits = dict(zip('一二三四五六七八九', range(1,10)))
                if '十' in text:
                    left, right = text.split('十')
                    chapter = (digits.get(left, 1) * 10 + digits.get(right, 0))
                else:
                    chapter = digits.get(text, 999)
        return (route[0], chapter)
    return sorted(routes, key=route_key)


def execute_mission(self, ocr, num_want, num_challenge):
    # Use the exact progress box identified by find_wq. Passing the broad
    # Full OCR rule to ui_click reruns detection and can click another sidebar
    # item (for example a timed Nian beast above the tracked bounty).
    try:
        x, y, w, h = (int(v) for v in ocr.area)
    except (AttributeError, TypeError, ValueError) as exc:
        raise GameStuckError('Missing sender quest progress coordinates') from exc
    if not (12 <= x < 100 and 119 <= y < 512 and 0 < w <= 88 and
            0 < h <= 60 and x + w <= 105 and y + h <= 512):
        raise GameStuckError('Invalid sender quest progress coordinates')
    target = RuleClick((x, y, w, h), (x, y, w, h), name='findjade_tracked_progress')
    self.screenshot()
    if not self.appear(self.I_TRACE_TRUE):
        if not self.sender_exploration_visible():
            raise GameStuckError('Sender exploration no longer visible before opening quest')
        self.click(target)
        deadline = monotonic() + 10
        while monotonic() < deadline:
            sleep(.2)
            self.screenshot()
            if self.appear(self.I_TRACE_TRUE):
                break
        else:
            raise GameStuckError('Cannot open sender quest destination details')
    if not hasattr(self,'sender_excluded_routes'):
        self.sender_excluded_routes=set()
    routes = self.sender_routes(self.device.image,num_challenge)
    if not routes:
        raise GameStuckError('No available sender quest route: all Go buttons are missing, locked, or excluded')
    _,destination,per_battle,button,kind=routes[0]
    count=(num_want+per_battle-1)//per_battle
    batch_count = 1 if kind in ('秘闻', '探索') else count
    logger.info('FindJade selected available route: %s %s, count=%s',kind,destination,batch_count)
    action={'挑战':self.challenge,'探索':self.explore,'秘闻':self.secret,'御魂':self.sender_soul}[kind]
    try:
        # Secret zones may automatically select the next unlocked floor.
        # Re-enter the bounty recommendation after every battle to stay on
        # the named floor and verify actual target progress.
        action(button,batch_count)
        progress = getattr(self, 'sender_selected_progress', None)
        if progress is not None:
            self.sender_last_route_result = (*progress, (kind, destination))
    except ExploreWantedBoss:
        self.sender_excluded_routes.add((kind,destination))
        logger.info('FindJade exploration route exhausted; recheck sender progress before choosing another route')


def sender_soul(self, goto, count):
    fire = OrochiAssets.I_OROCHI_FIRE
    if not self.ui_click(goto,fire,interval=1,timeout=15):
        raise GameStuckError('Cannot enter the bounty-recommended soul layer')
    for _ in range(count):
        self.screenshot()
        self.appear_then_click(OrochiAssets.I_OROCHI_UNLOCK,interval=1)
        deadline=monotonic()+15
        while monotonic()<deadline:
            self.screenshot()
            if not self.appear(fire):
                break
            self.appear_then_click(fire,interval=1)
        else:
            raise GameStuckError('Soul challenge button did not start battle')
        if not self.run_general_battle(GeneralBattleConfig(lock_team_enable=True)):
            raise SenderBattleFailed('Sender soul battle did not succeed')
        deadline=monotonic()+20
        while monotonic()<deadline:
            self.screenshot()
            if self.clear_sender_settlement():
                continue
            if self.appear(fire):
                break
        else:
            raise GameStuckError('Cannot confirm return to soul challenge after battle')
    self.enter_sender_exploration()


def sender_fire(self, button):
    """Never continue an exploration after an unambiguous battle loss."""
    # Do not spend a throttled click-until-disappear loop on the enemy
    # marker: the preparation countdown may expire before assist inspection.
    self.screenshot()
    if not self.appear(button):
        return False
    from tasks.FindJade.assist import prepare_exploration_assist_entry
    prepare_exploration_assist_entry(self)
    # The OCR above does not move the map; rematch the enemy before clicking.
    if not self.appear(button):
        return False
    self.device.save_screenshot(genre='findjade_before_enemy', interval=0)
    x, y = button.coord()
    self.device.click(int(x), int(y), control_name='sender_enemy_start')
    deadline = monotonic() + 20
    retry_at = monotonic() + 2
    clicks = 1
    while monotonic() < deadline:
        self.screenshot()
        if (self.appear(self.I_PREPARE_HIGHLIGHT) or self.is_in_real_battle(False)
                or self.battle_result_visible()):
            break
        if monotonic() >= retry_at and clicks < 3 and self.appear(button):
            x, y = button.coord()
            self.device.click(int(x), int(y), control_name='sender_enemy_retry')
            clicks += 1
            retry_at = monotonic() + 2
        sleep(.1)
    else:
        self.device.save_screenshot(genre='findjade_enemy_click_timeout', interval=0)
        raise GameStuckError('探索点击后未确认准备或战斗页面')
    if not self.run_general_battle(self._config.general_battle_config):
        raise SenderBattleFailed('协作探索战斗失败，已停止避免重复消耗体力')
    self.minions_cnt += 1
    return True
