"""Apprentice solo soul floor one, with crash-safe confirmed-win accounting."""
from module.config.local_values import local_text
import json
import hashlib
import os
import time
import re
from datetime import date
from pathlib import Path

import cv2
import numpy as np
from module.atom.ocr import RuleOcr
from module.exception import GameNotRunningError, GameStuckError
from module.logger import logger
from tasks.GameUi.page import page_main, page_soul_zones
from tasks.Orochi.script_task import ScriptTask as OrochiTask
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from .vision import detect


class NoAssistShikigami(Exception):
    """The apprentice has no assist shikigami available for souls."""


def _assist_card(image, allowed_limits=(15,), allow_multiple=False):
    """Check the crossed swords on the same card as the assist counter.

    None means that the card or its marker could not be identified safely.
    """
    reader = RuleOcr(roi=(210, 580, 870, 100), area=(210, 580, 870, 100),
                     mode='Full', method='Default', keyword='', name='mentorship_assist_count')
    matches = []
    for item in reader.detect_and_ocr(image):
        count = re.search(r'(?<!\d)(\d{1,2})\s*[/／]\s*(\d{1,2})(?!\d)', item.ocr_text)
        if count and int(count.group(2)) in allowed_limits and 0 <= int(count.group(1)) <= int(count.group(2)):
            x = 210 + int(np.mean(item.box[:, 0]))
            y = 580 + int(np.mean(item.box[:, 1]))
            matches.append((x, y, int(count.group(1)), int(count.group(2))))
    if not matches or (len(matches) != 1 and not allow_multiple):
        return None, None
    template = cv2.imdecode(np.fromfile(str(Path(__file__).parent / 'assets' / 'assist_deployed.png'), dtype=np.uint8), cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError('assist_deployed.png')
    deployed, available, exhausted = [], [], []
    for x, y, used, limit in matches:
        if used >= limit:
            exhausted.append((x,y))
            continue
        region = cv2.cvtColor(image[max(0, y-160):max(0, y-90), max(0, x-80):min(1280, x+25)], cv2.COLOR_RGB2BGR)
        if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
            continue
        score = float(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED).max())
        if score >= .8:
            deployed.append((x,y))
        elif score < .55:
            available.append((used/limit,x,y))
    if len(deployed)==1:
        return 'deployed', deployed[0]
    if len(deployed)>1:
        return None, None
    if available:
        _,x,y=min(available)
        return 'available', (x,y)
    if len(exhausted)==len(matches):
        return 'exhausted', exhausted[0]
    return None, None


def _assist_in_lineup(image):
    state, _ = _assist_card(image)
    return True if state == 'deployed' else False if state in ('available', 'exhausted') else None


def _leave_preparation(task, device):
    """Leave without starting and positively confirm the soul selection page."""
    deadline = time.monotonic() + 45
    last_click = 0
    while time.monotonic() < deadline:
        device.screenshot()
        if detect(device.image, 'orochi_selected_one') and task.I_OROCHI_FIRE.match(device.image):
            return True
        if time.monotonic() - last_click >= 1.5:
            if task.I_FALSE.match(device.image):
                device.click(*task.I_FALSE.coord(), control_name='mentorship_assist_exit_result')
                last_click = time.monotonic()
            elif task.I_EXIT_ENSURE.match(device.image):
                device.click(*task.I_EXIT_ENSURE.coord(), control_name='mentorship_assist_exit_confirm')
                last_click = time.monotonic()
            elif task.I_EXIT.match(device.image):
                device.click(*task.I_EXIT.coord(), control_name='mentorship_assist_exit')
                last_click = time.monotonic()
        time.sleep(.2)
    return False


def _set_souls_lock(task, device, locked):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        device.screenshot()
        if not detect(device.image, 'orochi_selected_one'):
            raise RuntimeError('御魂壹层选中状态未确认')
        wanted = task.I_OROCHI_LOCK if locked else task.I_OROCHI_UNLOCK
        other = task.I_OROCHI_UNLOCK if locked else task.I_OROCHI_LOCK
        if wanted.match(device.image):
            return
        if other.match(device.image):
            device.click(*other.coord(), control_name='mentorship_souls_lock' if locked else 'mentorship_souls_unlock')
            time.sleep(.8)
        else:
            time.sleep(.2)
    raise RuntimeError('徒弟御魂阵容锁定状态未确认')


def _save(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def run_apprentice_souls(config, device, rounds=15, day=None, character=local_text('LOCAL_SUPPORT_004'), server='砂狐乐园'):
    if config.config_name != 'oas_leveling' or rounds != 15:
        raise ValueError('徒弟御魂配置不匹配')
    day = day or date.today()
    identity = hashlib.sha256((server + '\0' + character).encode('utf-8')).hexdigest()[:16]
    directory = Path('log/mentorship') / config.config_name
    path = directory / ('souls_' + day.isoformat() + '_' + identity + '.json')
    legacy = directory / ('souls_' + day.isoformat() + '.json')
    if (not path.exists() and day.isoformat() == '2026-11-03'
            and character == local_text('LOCAL_SUPPORT_004') and server == '砂狐乐园' and legacy.exists()):
        # This day's legacy run was observed on this specific apprentice.
        old = json.loads(legacy.read_text(encoding='utf-8'))
        old.update(character=character, server=server)
        _save(path, old)
    record = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'date': day.isoformat(), 'character': character, 'server': server,
        'confirmed_wins': 0, 'pending': False,
    }
    wins = record.get('confirmed_wins')
    if (record.get('date') != day.isoformat() or record.get('character') != character
            or record.get('server') != server or type(wins) is not int
            or not 0 <= wins <= rounds or type(record.get('pending')) is not bool):
        raise RuntimeError(f'御魂进度有未确认的战斗，请先核对 {path}')
    unresolved = record.get('unresolved_battles', 0)
    if type(unresolved) is not int or not 0 <= unresolved <= rounds:
        raise RuntimeError(f'御魂进度记录不合法，请先核对 {path}')
    if record.get('preparing', False):
        raise RuntimeError(f'御魂准备阶段曾中断，请核对现场后恢复 {path}')
    if wins == rounds:
        return wins

    task = OrochiTask(config, device)
    if not task.ui_goto_page(page_soul_zones, timeout=35):
        raise RuntimeError('徒弟无法打开御魂入口')
    if not task.orochi_enter() or not task.check_layer('壹层'):
        raise RuntimeError('徒弟无法选择御魂壹层')
    if record['pending']:
        device.screenshot()
        if not (detect(device.image, 'orochi_selected_one') and task.I_OROCHI_FIRE.match(device.image)):
            raise RuntimeError('未确认退出上次御魂战斗，进度保留待核对')
        unresolved += 1
        record.update(pending=False, unresolved_battles=unresolved)
        _save(path, record)
    # Keep fighting until `rounds` battles are *confirmed*. An unresolved round
    # stays in the record for audit, but it must not shorten the plan, otherwise
    # a single unreadable result locks the day out of its 15 confirmed wins.
    safe_limit = rounds
    # The first preparation screen must be visible before any auto-ready.
    _set_souls_lock(task, device, False)

    battle_config = GeneralBattleConfig()
    assist_verified = False
    while wins < safe_limit:
        device.screenshot()
        if not (detect(device.image, 'orochi_selected_one') and task.I_OROCHI_FIRE.match(device.image)):
            raise RuntimeError('御魂壹层挑战页未确认')
        record['preparing'] = True
        _save(path, record)
        device.click(*task.I_OROCHI_FIRE.coord(), control_name='mentorship_souls_start')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            device.screenshot()
            if not task.I_OROCHI_FIRE.match(device.image):
                break
            time.sleep(.2)
        else:
            raise RuntimeError('御魂战斗未确认开始，进度标记为待核对')
        if not assist_verified:
            deadline = time.monotonic() + 25
            exhausted_frames = 0
            drag_attempts = 0
            next_drag = 0.0
            panel_attempts = iter(((640, 430), (460, 500), (805, 500), (640, 570), (460, 430)))
            next_panel_click = 0.0
            while time.monotonic() < deadline:
                device.screenshot()
                if task.is_in_real_battle(False) or task.battle_result_visible():
                    record.update(preparing=False, pending=True)
                    _save(path, record)
                    raise RuntimeError('协战检查前已进入战斗，进度标记为待核对')
                if task.I_PREPARE_HIGHLIGHT.match(device.image):
                    assist_state, card = _assist_card(device.image)
                    if assist_state is None and time.monotonic() >= next_panel_click:
                        position = next(panel_attempts, None)
                        if position is not None:
                            device.click(*position, control_name='mentorship_open_lineup')
                            next_panel_click = time.monotonic() + 1
                            time.sleep(.8)
                            continue
                    if assist_state == 'deployed':
                        assist_verified = True
                        break
                    if assist_state == 'available' and drag_attempts < 2 and time.monotonic() >= next_drag:
                        x, y = card
                        # The counter sits near the bottom of its card. Drag
                        # the card body to the middle deployed-unit slot.
                        device.swipe((x - 18, y - 75), (640, 340), duration=1.2,
                                     control_name='mentorship_deploy_assist', distance_check=False)
                        drag_attempts += 1
                        next_drag = time.monotonic() + 2
                        time.sleep(1)
                        continue
                    exhausted_frames = exhausted_frames + 1 if assist_state == 'exhausted' else 0
                    if exhausted_frames >= 3:
                        device.save_screenshot(genre='mentorship_assist_not_deployed', interval=0)
                        logger.warning('徒弟协战式神次数已用完，改为无协战继续御魂')
                        assist_verified = True
                        break
                time.sleep(.4)
            else:
                logger.warning('未能确认徒弟协战是否上阵，继续御魂战斗')
                assist_verified = True
        record.update(pending=True, preparing=False)
        _save(path, record)
        try:
            won = task.run_general_battle(config=battle_config)
        except (GameStuckError, GameNotRunningError) as error:
            # The client can leave the battle and sit back on the challenge
            # page without any reward marker the generic wait recognises. The
            # round stays unresolved (it is excluded from safe_limit) instead
            # of stopping the whole mentorship plan.
            device.screenshot()
            if not detect(device.image, 'orochi_selected_one'):
                raise
            logger.warning(f'御魂战斗结果未能识别（{error}），已回到壹层，保留待核对')
            break
        if not won:
            raise RuntimeError('御魂战斗失败，进度标记为待核对')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            device.screenshot()
            if detect(device.image, 'orochi_selected_one') and task.I_OROCHI_FIRE.match(device.image):
                break
            time.sleep(.2)
        else:
            raise RuntimeError('御魂胜利后未确认返回壹层，进度标记为待核对')
        wins += 1
        record.update(confirmed_wins=wins, pending=False)
        _save(path, record)
        print(f'APPRENTICE_SOULS_CONFIRMED {wins}/{rounds}', flush=True)
        if wins < safe_limit and assist_verified:
            _set_souls_lock(task, device, True)
    task.ui_goto_page(page_main, timeout=35)
    if unresolved:
        # Unresolved rounds are already excluded from safe_limit, so the plan
        # cannot exceed its daily round budget; warn and let the rest of the
        # mentorship plan continue instead of stopping the scheduler.
        logger.warning(f'御魂已确认 {wins} 场，另有 {unresolved} 场结果待核对')
    return wins
