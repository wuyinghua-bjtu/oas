"""Single-account fire awakening farming with per-account daily drop evidence."""
import json
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.exception import GameStuckError, ScriptEnd, TaskEnd
from module.logger import logger
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.RightActivity.assets import RightActivityAssets
from tasks.EvoZone.script_task import ScriptTask as EvoTask
from tasks.EyeAwakening.progress import MAP_EYE, ProgressUncertain, read_map_quota, read_drop_popup_quota
from tasks.EyeAwakening.inventory import InventoryUncertain, read_inventory_frame, combine_boundaries
from tasks.EyeAwakening.notification import notify_completion
from tasks.EyeAwakening.profile import PROFILES, validate_profile
from tasks.FindJade.script_task import ScriptTask as FindJadeTask
from tasks.GameUi.page import page_awake_zones, page_exploration, page_main
from tasks.EyeAwakening.config import resolve_eye_accounts
from tasks.MetaDemon.assets import MetaDemonAssets as MD


ONE_SELECTED = RuleImage(roi_front=(94, 106, 128, 39), roi_back=(88, 98, 150, 55),
                         method='Template matching', threshold=0.8,
                         file='./tasks/EyeAwakening/one_selected.png')
ONE_CLICK = RuleClick((130, 112, 45, 25), (130, 112, 45, 25), 'eye_awakening_one')
BACK = RuleClick((27, 25, 25, 23), (27, 25, 25, 23), 'eye_awakening_back')
NICK = RuleOcr(roi=(125,25,150,32), area=(125,25,150,32), mode='Single',
               method='Default', keyword='', name='eye_account_name')


def one_selected(image):
    """Require the red selected background as well as the layer-one template."""
    if image is None or image.shape[0] < 143 or image.shape[1] < 225:
        return False
    region = image[110:143, 97:225, :3].astype('int16')
    red, green, blue = region[:, :, 0], region[:, :, 1], region[:, :, 2]
    selected = (red > 90) & (red * 2 > green * 3) & (red * 10 > blue * 13)
    return selected.mean() > .45 and ONE_SELECTED.match(image)


class ScriptTask(EvoTask):
    def open_inventory(self):
        if not self.ui_goto(page_main):
            raise InventoryUncertain('未能返回庭院查看库存')
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            self.screenshot()
            if self.appear(MD.I_CRAFT_TITLE_2026):
                return
            if self.appear_then_click(MD.I_CRAFTING_1, interval=2):
                continue
            if self.appear_then_click(MD.I_ENTER2, interval=2):
                continue
            if self.appear_then_click(MD.I_RIGHT_ENTER, interval=2):
                continue
            if self.appear(self.I_CHECK_MAIN):
                self.appear_then_click(RightActivityAssets.I_TOGGLE_BUTTON, interval=3)
            time.sleep(.4)
        raise InventoryUncertain('未能确认进入裂变之眼合成列表')

    def inventory_boundary(self, to_top):
        # The input is a drag on the item list, never an item or purchase click.
        previous = None
        stable = 0
        result = None
        start, end = ((380, 230), (380, 560)) if to_top else ((380, 560), (380, 230))
        for _ in range(7):
            self.screenshot()
            if not self.appear(MD.I_CRAFT_TITLE_2026):
                raise InventoryUncertain('库存窗口已变化')
            current = self.device.image[145:650, 200:560, :3].copy()
            if previous is not None:
                delta = np.abs(current.astype('int16') - previous.astype('int16')).mean()
                stable = stable + 1 if delta < 1.0 else 0
            if stable >= 2:
                result = read_inventory_frame(self.device.image)
                time.sleep(.5)
                self.screenshot()
                if not self.appear(MD.I_CRAFT_TITLE_2026):
                    raise InventoryUncertain('库存窗口已变化')
                if result != read_inventory_frame(self.device.image):
                    raise InventoryUncertain('库存数量两次识别不一致')
                return result
            previous = current
            self.device.swipe(start, end, duration=.7, control_name='eye_inventory_scroll',
                              distance_check=False)
            time.sleep(.8)
        raise InventoryUncertain('库存列表未确认滚动边界')

    def inventory_counts(self):
        self.open_inventory()
        top = self.inventory_boundary(True)
        bottom = self.inventory_boundary(False)
        # The rows are sorted by star and there are at most six kinds. With
        # both scroll boundaries confirmed, top and bottom cover all rows.
        return combine_boundaries(top, bottom)

    def leave_inventory(self):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self.screenshot()
            if self.appear(self.I_CHECK_MAIN):
                self.ui_current = page_main
                return
            if self.appear(MD.I_CRAFT_TITLE_2026):
                self.appear_then_click(MD.I_CRAFT_CLOSE_2026, interval=1.5)
            elif (self.appear(MD.I_CRAFTING_1) or self.appear(MD.I_ENTER2)):
                self.click(BACK, interval=1.5)
            time.sleep(.4)
        raise GameStuckError('库存核对后无法确认返回庭院')

    def map_visible(self):
        return MAP_EYE.match(self.device.image) and self.appear(self.I_EXPLORATION_GOTO_AWAKE_ZONE)

    def ui_page_appear(self, page, skip_first_screenshot=True, interval=None):
        if page is page_exploration:
            self.maybe_screenshot(skip_first_screenshot)
            if self.map_visible():
                return True
        return super().ui_page_appear(page, skip_first_screenshot, interval)

    def enter_map(self):
        box = (243, 100, 933, 211)
        reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                         keyword='', name='eye_exploration_entry')
        deadline, last_click = time.monotonic() + 35, 0
        while time.monotonic() < deadline:
            self.screenshot()
            if self.map_visible():
                self.ui_current = page_exploration
                return
            if self.appear(self.I_CHECK_MAIN) and time.monotonic() - last_click >= 3:
                rows = [row for row in reader.detect_and_ocr(self.device.image)
                        if row.ocr_text.replace(' ', '') == '探索']
                if len(rows) == 1:
                    points = rows[0].box
                    self.device.click(int(box[0] + points[:, 0].mean()),
                                      int(box[1] + points[:, 1].mean()),
                                      control_name='eye_exploration_entry')
                    last_click = time.monotonic()
            time.sleep(.4)
        raise GameStuckError('未能确认从庭院进入探索地图或活动入口未开放')

    def verified_identity(self, expected):
        self.ui_get_current_page()
        if not self.ui_goto(page_main):
            raise GameStuckError('无法回庭院核对角色')
        values = []
        for _ in range(2):
            self.screenshot()
            values.append((NICK.ocr(self.device.image) or '').replace(' ', '').strip())
            time.sleep(.4)
        if values != [expected, expected]:
            raise GameStuckError(f'角色身份未确认：期望 {expected}，识别 {values}')

    def map_progress(self):
        reads = []
        for _ in range(3):
            self.screenshot()
            if not self.map_visible():
                raise GameStuckError('未确认探索地图，不能读取掉落进度')
            try:
                reads.append(read_map_quota(self.device.image))
            except ProgressUncertain:
                reads.append(None)
            if len(reads) >= 2 and reads[-1] is not None and reads[-1] == reads[-2]:
                return reads[-1][0]
            time.sleep(.5)
        raise GameStuckError(f'裂变之眼掉落进度未能连续两次确认：{reads}')

    def enter_fire_one(self):
        if not self.ui_goto(page_awake_zones):
            raise GameStuckError('无法进入觉醒之塔')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self.screenshot()
            if self.appear(self.I_FORM_TEAM) and self.appear(self.I_EVOZONE_FIRE):
                break
            self.appear_then_click(self.I_FIRE_KIRIN, interval=2)
            time.sleep(.3)
        else:
            raise GameStuckError('未确认火麒麟挑战界面')
        for _ in range(5):
            self.screenshot()
            if one_selected(self.device.image):
                return
            self.click(ONE_CLICK, interval=.8)
            time.sleep(.6)
        raise GameStuckError('未确认火麒麟一层已选中')

    def return_to_map(self):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            self.screenshot()
            if self.map_visible():
                self.ui_current = page_exploration
                return
            if self.appear(self.I_FORM_TEAM) or self.appear(self.I_CHECK_AWAKE):
                self.click(BACK, interval=1.5)
            time.sleep(.4)
        raise GameStuckError('战斗后未确认返回探索地图')

    def battle_settlement_requires_confirmation(self):
        return True

    def finish_battle_settlement(self, win, timeout=45):
        if not win:
            raise GameStuckError('觉醒战斗失败，保留现场')
        deadline = time.monotonic() + timeout
        returned = 0
        while time.monotonic() < deadline:
            self.screenshot()
            try:
                count, total = read_drop_popup_quota(self.device.image)
            except ProgressUncertain:
                count = None
            if count is not None:
                logger.info('掉落弹窗进度 %s/%s', count, total)
                self.click(self.C_REWARD_1, interval=1)
                returned = 0
            elif self.appear(self.I_WIN) or self.appear(self.I_DE_WIN):
                self.click(self.C_WIN_1, interval=1)
                returned = 0
            elif self.appear(self.I_REWARD) or self.appear(self.I_REWARD_GOLD):
                self.click(self.C_REWARD_1, interval=1)
                returned = 0
            elif self.appear(self.I_FORM_TEAM) and self.appear(self.I_EVOZONE_FIRE):
                returned += 1
                if returned >= 2:
                    return True
            else:
                returned = 0
            time.sleep(.3)
        raise GameStuckError('觉醒结算后未确认返回火麒麟界面')

    def run(self):
        if self.config.config_name not in ('oas_leveling', *PROFILES):
            raise ScriptEnd('小号刷裂变之眼仅支持指定的小号配置')
        if self.config.config_name in PROFILES:
            try:
                validate_profile(self.config)
            except Exception as error:
                raise ScriptEnd('小号设备隔离检查失败：' + str(error)) from error
        try:
            accounts = resolve_eye_accounts(self.config.model.eye_awakening)
        except ValueError as error:
            self.config.model.eye_awakening.scheduler.enable = False
            self.config.save()
            raise ScriptEnd('小号名单配置不正确：' + str(error)) from error
        today = datetime.now().strftime('%Y-%m-%d')
        directory = Path('log/EyeAwakening') / self.config.config_name
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (today + '.json')
        servers = list(dict.fromkeys(account.svr for account in accounts))
        server_key = servers[0] if len(servers) == 1 else '\n'.join(servers)
        state = json.loads(path.read_text(encoding='utf8')) if path.exists() else {
            'date': today, 'server': server_key, 'accounts': {}, 'status': '运行中'}
        if state.get('server') != server_key:
            self.config.model.eye_awakening.scheduler.enable = False
            self.config.save()
            raise ScriptEnd('当天记录的服务器与当前配置不符')
        state['status'] = '运行中'
        current = ''
        stage = '准备'

        def save():
            state['updated_at'] = datetime.now().isoformat(timespec='seconds')
            tmp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf8')
            tmp.replace(path)

        try:
            for account in accounts:
                if datetime.now().strftime('%Y-%m-%d') != today:
                    raise GameStuckError('跨日后停止，等待重新确认当日掉落进度')
                current = account.character
                entry = state['accounts'].setdefault(current, {'battles': 0})
                notify_status = entry.get('notification', {}).get('status')
                if entry.get('completed') is True and entry.get('progress') == 50 and notify_status in ('accepted', 'sending', 'uncertain'):
                    if notify_status == 'sending':
                        entry['notification']['status'] = 'uncertain'
                        save()
                        logger.warning('%s 上次推送中断，结果未知，不自动重复发送', current)
                    continue
                if entry.get('battle_pending'):
                    raise GameStuckError(f'{current} 上次战斗结果未核对，需人工确认现场')
                stage = '切号及核对身份'
                if not FindJadeTask.switch_support_account(self, account):
                    raise GameStuckError('切换小号失败')
                self.verified_identity(current)
                stage = '读取探索地图进度'
                self.enter_map()
                progress = self.map_progress()
                entry.update(progress=progress, verified_at=datetime.now().isoformat(timespec='seconds'))
                save()
                while progress < 50:
                    if datetime.now().strftime('%Y-%m-%d') != today:
                        raise GameStuckError('跨日后停止，等待重新确认当日掉落进度')
                    if entry['battles'] >= self.config.model.eye_awakening.options.max_battles_per_account:
                        raise GameStuckError(f'{current} 达到战斗次数上限，进度 {progress}/50')
                    stage = '进入火麒麟一层'
                    self.enter_fire_one()
                    self.screenshot()
                    if not (one_selected(self.device.image) and self.appear(self.I_EVOZONE_FIRE)):
                        raise GameStuckError('挑战前未确认火麒麟一层')
                    entry['battle_pending'] = True
                    save()
                    stage = '觉醒战斗与结算'
                    if not self.click(self.I_EVOZONE_FIRE, interval=1):
                        raise GameStuckError('挑战按钮未点击，保留待核对记录')
                    self.current_count = 0
                    if not self.run_general_battle(GeneralBattleConfig()):
                        raise GameStuckError('觉醒战斗失败')
                    stage = '战后核对掉落进度'
                    self.return_to_map()
                    new_progress = self.map_progress()
                    if new_progress < progress:
                        raise GameStuckError(f'掉落进度倒退 {progress}→{new_progress}，停止核对')
                    progress = new_progress
                    entry.update(progress=progress, battles=entry['battles'] + 1,
                                 verified_at=datetime.now().isoformat(timespec='seconds'))
                    entry.pop('battle_pending', None)
                    save()
                    logger.info('%s 裂变之眼 %s/50，已完成 %s 场', current, progress, entry['battles'])
                entry['completed'] = True
                save()
                stage = '核对五星和六星库存'
                counts = {5: None, 6: None}
                try:
                    counts = self.inventory_counts()
                    entry.pop('inventory_error', None)
                except Exception as error:
                    entry['inventory_error'] = str(error) or type(error).__name__
                    logger.warning('%s 库存未完整识别：%s', current, type(error).__name__)
                entry['inventory'] = {'five_star': counts[5], 'six_star': counts[6],
                                      'verified_at': datetime.now().isoformat(timespec='seconds')}
                # A crash during a network call has an ambiguous outcome; do
                # not retry it automatically and produce duplicate messages.
                stage = '推送完成结果'
                entry['notification'] = {'status': 'sending',
                                         'attempted_at': datetime.now().isoformat(timespec='seconds')}
                save()
                status = notify_completion(self.config, current, counts, account.account)
                entry['notification']['status'] = status
                save()
                logger.info('%s 完成推送状态：%s', current, status)
                stage = '库存核对后返回庭院'
                self.leave_inventory()
            state['status'] = '完成'
            save()
        except Exception as error:
            state['status'] = '出错'
            state['failure'] = {'character': current, 'stage': stage, 'reason': str(error)}
            save()
            logger.exception(error)
            raise ScriptEnd(f'小号刷裂变之眼停止：{current} {stage}：{error}') from error
        finally:
            self.config.model.eye_awakening.scheduler.enable = False
            self.config.save()
        raise TaskEnd('EyeAwakening')
