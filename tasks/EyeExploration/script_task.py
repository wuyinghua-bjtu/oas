"""Solo exploration, stopping on the verified event drop quota."""
import json
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from module.exception import GameStuckError, ScriptEnd, TaskEnd
from module.logger import logger
from tasks.EyeAwakening.progress import MAP_EYE, ProgressUncertain, read_drop_popup_quota
from tasks.EyeAwakening.script_task import NICK, ScriptTask as EyeAwakeningTask
from tasks.EyeExploration.progress import read_reward_quota
from tasks.Exploration.base import Scene
from tasks.Exploration.solo import ScriptTask as ExplorationTask
from tasks.GameUi.page import page_exploration, page_main


class ScriptTask(ExplorationTask):
    def __init__(self, config, device):
        super().__init__(config, device)
        # BaseExploration mutates exploration settings. Keep all temporary
        # changes in an isolated model and preserve the real configuration.
        self.original_config = config
        isolated = object.__new__(type(config))
        isolated.__dict__.update(config.__dict__)
        isolated.model = config.model.model_copy(deep=True)
        self.config = isolated
        opts = config.model.eye_exploration.options
        self.config.model.exploration.exploration_config.exploration_level = opts.exploration_level
        self.explore_init = False
        self.minions_cnt = 0
        self.progress_current = None
        self.stop_reason = None
        self.state = None
        self.entry = None
        self.save_state = None

    def map_visible(self):
        return MAP_EYE.match(self.device.image) and self.appear(self.I_EXPLORATION_GOTO_AWAKE_ZONE)

    def ui_page_appear(self, page, skip_first_screenshot=True, interval=None):
        if page is page_exploration:
            self.maybe_screenshot(skip_first_screenshot)
            if self.map_visible():
                return True
        return super().ui_page_appear(page, skip_first_screenshot, interval)

    def get_current_scene(self, reuse_screenshot=True):
        if not reuse_screenshot:
            self.screenshot()
        if self.map_visible() and not self.appear(self.I_E_SETTINGS_BUTTON):
            return Scene.WORLD
        return super().get_current_scene(reuse_screenshot=True)

    def battle_settlement_requires_confirmation(self):
        return True

    def finish_battle_settlement(self, win, timeout=60):
        if not win:
            raise GameStuckError('探索战斗失败，保留结算现场')
        deadline = time.monotonic() + timeout
        previous = None
        verified = None
        while time.monotonic() < deadline:
            self.screenshot()
            try:
                current = read_drop_popup_quota(self.device.image)
                popup = True
            except ProgressUncertain:
                current, popup = None, False
            if current is None and (self.appear(self.I_REWARD) or self.appear(self.I_REWARD_GOLD)):
                try:
                    current = read_reward_quota(self.device.image)
                except ProgressUncertain:
                    current = None
            if current is not None:
                if previous == current:
                    if self.progress_current is not None and current[0] < self.progress_current:
                        raise GameStuckError('裂变之眼结算进度倒退')
                    verified = current[0]
                    self.progress_current = verified
                    self.entry['observed_reward_progress'] = verified
                    self.save_state()
                    self.click(self.C_REWARD_1, interval=1)
                previous = current
            elif self.appear(self.I_WIN) or self.appear(self.I_DE_WIN):
                self.click(self.C_WIN_1, interval=1)
            elif self.get_current_scene() == Scene.MAIN:
                if verified is None:
                    raise GameStuckError('战斗已返回探索，但未确认结算掉落进度')
                return True
            time.sleep(.3)
        raise GameStuckError('探索结算未能确认掉落进度和返回章节')

    def check_exit(self):
        self.screenshot()
        if self.map_visible():
            progress = EyeAwakeningTask.map_progress(self)
            if self.progress_current is not None and progress < self.progress_current:
                raise GameStuckError('探索地图掉落进度倒退')
            self.progress_current = progress
            self.entry.update(progress=progress, verified_at=datetime.now().isoformat(timespec='seconds'))
            self.save_state()
        elif self.appear(self.I_E_EXPLORATION_CLICK) and self.progress_current is not None:
            progress = self.progress_current
        else:
            raise GameStuckError('未确认探索地图或章节入口，不能判断是否继续')
        if progress == 50:
            self.stop_reason = '完成'
            return True
        if self.minions_cnt >= self.original_config.model.eye_exploration.options.max_battles:
            self.stop_reason = '战斗次数上限'
            return True
        if datetime.now() - self.start_time >= self.limit_time:
            self.stop_reason = '时间上限'
            return True
        return False

    def quit_explore(self):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            self.screenshot()
            if self.map_visible():
                self.ui_current = page_exploration
                return
            if self.appear_then_click(self.I_BATTLE_REWARD, interval=1.5):
                continue
            if self.appear_then_click(self.I_E_EXIT_CONFIRM, interval=1):
                continue
            if self.appear(self.I_E_EXPLORATION_CLICK):
                if self.appear_then_click(self.I_UI_BACK_RED, interval=1.5):
                    continue
                if self.appear_then_click(self.I_UI_BACK_YELLOW, interval=1.5):
                    continue
            elif self.appear(self.I_E_SETTINGS_BUTTON) or self.appear(self.I_E_AUTO_ROTATE_ON) or self.appear(self.I_E_AUTO_ROTATE_OFF):
                self.appear_then_click(self.I_BACK_YOLLOW, interval=1.5)
            time.sleep(.3)
        raise GameStuckError('无法确认退出探索章节，保留现场')

    def fire(self, button):
        if datetime.now().date().isoformat() != self.state['date']:
            raise GameStuckError('跨日后停止，需重新确认当日掉落进度')
        self.entry['battle_pending'] = True
        self.save_state()
        won = super().fire(button)
        if not won:
            self.screenshot()
            if self.get_current_scene() != Scene.MAIN:
                raise GameStuckError('探索挑战状态不明，保留待核对记录')
            self.entry.pop('battle_pending', None)
            self.save_state()
            return False
        self.entry.update(progress=self.progress_current, battles=self.entry.get('battles', 0) + 1,
                          verified_at=datetime.now().isoformat(timespec='seconds'))
        self.entry.pop('battle_pending', None)
        self.save_state()
        if (self.progress_current == 50 or
                self.minions_cnt >= self.original_config.model.eye_exploration.options.max_battles or
                datetime.now() - self.start_time >= self.limit_time):
            self.quit_explore()
        return True

    def run(self):
        if self.original_config.config_name != 'oas1':
            raise ScriptEnd('大号探索刷裂变之眼仅支持 oas1')
        today = datetime.now().date().isoformat()
        directory = Path('log/EyeExploration') / self.original_config.config_name
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (today + '.json')
        self.state = json.loads(path.read_text(encoding='utf8')) if path.exists() else {
            'date': today, 'accounts': {}, 'status': '运行中'}
        if self.state.get('date') != today:
            raise ScriptEnd('探索进度记录日期不符')

        def save():
            self.state['updated_at'] = datetime.now().isoformat(timespec='seconds')
            tmp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding='utf8')
            tmp.replace(path)
        self.save_state = save
        stage = '确认庭院账号'
        try:
            self.screenshot()
            if not self.appear(self.I_CHECK_MAIN):
                raise GameStuckError('请从大号庭院启动，避免接管其他任务')
            names = []
            for _ in range(2):
                self.screenshot()
                names.append((NICK.ocr(self.device.image) or '').replace(' ', '').strip())
                time.sleep(.4)
            if not names[0] or names[0] != names[1]:
                raise GameStuckError('庭院角色名未能稳定识别')
            character = names[0]
            self.entry = self.state['accounts'].setdefault(character, {'battles': 0})
            if self.entry.get('battle_pending'):
                raise GameStuckError('上次战斗结果未核对，需人工确认现场')
            self.state.update(status='运行中', character=character)
            self.state.pop('failure', None)
            save()
            self.ui_current = page_main
            stage = '进入探索地图'
            EyeAwakeningTask.enter_map(self)
            # Configure the cached limits from the isolated exploration copy.
            _ = self._config
            stage = '读取掉落进度并刷探索'
            self.run_solo()
            if self.stop_reason == '完成' and self.progress_current == 50:
                self.entry['completed'] = True
                self.state['status'] = '完成'
            else:
                self.state['status'] = '未完成'
                self.state['stop_reason'] = self.stop_reason or '未确认掉落上限'
            save()
            self.ui_current = page_exploration
            if not self.ui_goto(page_main):
                raise GameStuckError('退出后未确认返回庭院')
        except Exception as error:
            self.state['status'] = '出错'
            self.state['failure'] = {'stage': stage, 'reason': str(error)}
            save()
            logger.exception(error)
            raise ScriptEnd('探索刷裂变之眼停止：' + str(error)) from error
        finally:
            self.original_config.model.eye_exploration.scheduler.enable = False
            self.original_config.save()
        raise TaskEnd('EyeExploration')
