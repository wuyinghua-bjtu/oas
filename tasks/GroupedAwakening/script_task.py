"""Four teams, each completing fifteen awakening battles sequentially."""
import json
import subprocess
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import psutil
import win32api
import win32con
import win32gui

from module.exception import GameStuckError, GameSessionExpiredError, GameBlackScreenError, GameNotRunningError, ScriptEnd, TaskEnd
from module.logger import logger
from module.notify.notify import Notifier
from module.atom.ocr import RuleOcr
from tasks.Component.GeneralInvite.config_invite import InviteConfig, InviteNumber
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.EvoZone.config import KirinType, Layer
from tasks.FindJade.script_task import ScriptTask as FindJadeTask
from tasks.GuildQuickParticipation.policy import SUPPORT_CHARACTERS, SERVER
from tasks.TripleAwakening.script_task import (ScriptTask as TeamTask, Participant,
                                                 TeamBattleFailed, WINDOWS, MANAGER)
from tasks.TripleAwakening.device import TeamDevice
from tasks.GroupedAwakening.plan import GROUPS, resolve_accounts
from tasks.GroupedAwakening.session_guard import install_login_expiry_guard
from tasks.GroupedAwakening.ledger import atomic_json_write, finalize_settled_round
from tasks.GameUi.page import page_awake_zones
from tasks.Mentorship.apprentice_souls import _assist_card


def resumable_today(record, today):
    return (record.get('date') == today and
            record.get('status') not in ('完成', '完成（有失败）'))


def guild_changed_after_record(guild, saved_at):
    return not saved_at or not guild.get('updated_at') or guild['updated_at'] > saved_at


def restart_black_screen_game(device):
    """Restart only this bound game once during pre-battle login recovery."""
    if isinstance(device, TeamDevice):
        device.validate()
    package = device.package
    if package != 'com.netease.onmyoji':
        raise GameStuckError('黑屏恢复时游戏包名不匹配，停止重启')
    prefix = [device.adb_binary, '-s', device.serial, 'shell']
    try:
        subprocess.run(prefix + ['am', 'force-stop', package], check=True, timeout=15,
                       creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        subprocess.run(prefix + ['monkey', '-p', package, '-c', 'android.intent.category.LAUNCHER', '1'],
                       check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        raise GameStuckError('黑屏后重启游戏失败，模拟器可能无响应') from error
    logger.warning('Restarted black-screen game on %s during pre-battle login', device.serial)
    # Game startup can keep the render surface black for several seconds.
    time.sleep(20)


def keep_team_window_on_screen(title):
    """Keep GDI screenshots from silently including pixels beyond the desktop."""
    matches = []
    win32gui.EnumWindows(lambda h, _: matches.append(h) if win32gui.GetWindowText(h) == title else None, None)
    if len(matches) != 1:
        raise GameStuckError('模拟器窗口缺失或重名：' + title)
    hwnd = matches[0]
    x, y, right, bottom = win32gui.GetWindowRect(hwnd)
    left = win32api.GetSystemMetrics(76)
    top = win32api.GetSystemMetrics(77)
    screen_right = left + win32api.GetSystemMetrics(78)
    screen_bottom = top + win32api.GetSystemMetrics(79)
    width, height = right - x, bottom - y
    if width > screen_right - left or height > screen_bottom - top:
        raise GameStuckError('模拟器窗口超过桌面范围：' + title)
    new_x = max(left, min(x, screen_right - width))
    new_y = max(top, min(y, screen_bottom - height))
    if (new_x, new_y) != (x, y):
        win32gui.SetWindowPos(hwnd, 0, new_x, new_y, 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        logger.warning('Moved %s inside desktop to avoid clipped screenshots', title)


def lineup_prompt_visible(image):
    """Recognize the preparation screen's explicit lineup-configuration hint."""
    box = (450, 670, 450, 45)
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                     keyword='', name='group_lineup_prompt')
    text = ''.join(row.ocr_text for row in reader.detect_and_ocr(image)).replace(' ', '')
    return '式神区域' in text and '配置' in text


def lineup_target(image):
    """Locate the floating lineup hint, which moves with the player's unit."""
    box = (150, 200, 850, 350)
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                     keyword='', name='group_lineup_target')
    rows = reader.detect_and_ocr(image)
    labels = [row for row in rows if '出战式神配置' in row.ocr_text.replace(' ', '')]
    instructions = [row for row in rows if '点击此处进行' in row.ocr_text.replace(' ', '')]
    if len(labels) != 1 or len(instructions) != 1:
        return None
    label, instruction = labels[0].box, instructions[0].box
    lx, ly = float(label[:,0].mean()), float(label[:,1].mean())
    ix, iy = float(instruction[:,0].mean()), float(instruction[:,1].mean())
    if abs(lx-ix) > 50 or not 0 < ly-iy < 70:
        return None
    return (int(box[0]+(lx+ix)/2), int(box[1]+(ly+iy)/2))


class ScriptTask(TeamTask):
    @staticmethod
    def prepare_assists(players, record, save, timeout=25):
        """Prepare each window concurrently; preserve partial evidence on failure."""
        ocr_lock = threading.Lock()
        deadline = time.monotonic() + timeout

        def prepare(player):
            positions = iter(((640,430), (460,500), (805,500)))
            next_open = 0.0
            target_attempts = 0
            drags = 0
            last_drag = 0.0
            last_state = object()
            saved_initial = False
            capture_next = False
            evidence_dir = Path('log/GroupedAwakening/oas_leveling/assist_evidence')
            evidence_dir.mkdir(parents=True, exist_ok=True)

            def evidence(label):
                path = evidence_dir / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') +
                                       '_' + player.expected_name + '_' + label + '.png')
                player.device.image_save(path.resolve())
                logger.info('协战准备画面 %s: %s', player.expected_name, path)

            while time.monotonic() < deadline:
                player.screenshot()
                if player.is_in_real_battle(False) or player.battle_result_visible():
                    evidence('battle_or_result')
                    return '战斗或结算已出现，协战未确认'
                if not player.appear(player.I_PREPARE_HIGHLIGHT):
                    time.sleep(.1)
                    continue
                if not saved_initial or capture_next:
                    evidence('after_open' if capture_next else 'initial')
                    saved_initial = True
                    capture_next = False
                with ocr_lock:
                    state, card = _assist_card(player.device.image, allowed_limits=(15,30), allow_multiple=True)
                    target = lineup_target(player.device.image) if state is None else None
                    prompt = state is None and target is None and lineup_prompt_visible(player.device.image)
                if state != last_state:
                    logger.info('好友协战识别 %s: %s', player.expected_name, state or '未识别')
                    last_state = state
                if state == 'deployed':
                    return '已确认'
                if state == 'exhausted':
                    return '好友协战次数已用完'
                if state == 'available' and drags < 2 and time.monotonic()-last_drag >= 1.5:
                    x, y = card
                    player.device.swipe((x-18,y-75),(640,340),duration=1.2,
                                        control_name='group_deploy_friend_assist',distance_check=False)
                    drags += 1
                    last_drag = time.monotonic()
                elif target and target_attempts < 2 and time.monotonic() >= next_open:
                    # The floating hint itself is not interactive. Select the
                    # unit directly below it, then verify the card list.
                    x,y = target
                    player.device.click(x, min(y+85, 565),control_name='group_open_unit_below_hint')
                    target_attempts += 1
                    capture_next = True
                    next_open = time.monotonic() + .8
                elif prompt and time.monotonic() >= next_open:
                    position = next(positions, None)
                    if position is not None:
                        player.device.click(*position,control_name='group_open_lineup')
                        capture_next = True
                        next_open = time.monotonic() + .8
                time.sleep(.1)
            player.device.save_screenshot(genre='group_assist_'+player.expected_name,interval=0)
            return '未识别或未确认好友协战'

        with ThreadPoolExecutor(max_workers=len(players)) as executor:
            results = list(executor.map(prepare, players))
        record['assist_attempt'] = dict(zip((p.expected_name for p in players),results))
        if all(result == '已确认' for result in results):
            record['assist_verified'] = {p.expected_name: True for p in players}
        save()
        if not all(result == '已确认' for result in results):
            logger.warning('好友协战未全部确认，按设置继续战斗：%s', record['assist_attempt'])

    @staticmethod
    def assists_confirmed(players, record):
        evidence = record.get('assist_verified')
        names = [p.expected_name for p in players]
        return (isinstance(evidence, dict) and len(names) == len(set(names))
                and set(evidence) == set(names) and all(evidence[name] is True for name in names))

    @staticmethod
    def battle(players, final, record, save):
        if record.get('active_round') == 1 and 'assist_attempt' not in record:
            ScriptTask.prepare_assists(players, record, save)
        return TeamTask.battle(players, final, record, save)

    def run(self):
        if self.config.config_name != 'oas_leveling':
            raise ScriptEnd('分组觉醒仅支持 oas_leveling')
        directory = Path('log/GroupedAwakening/oas_leveling')
        directory.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime('%Y-%m-%d')
        pointer = directory / 'active.json'
        path = directory / (today + '.json')
        if pointer.exists():
            previous_path = directory / json.loads(pointer.read_text(encoding='utf-8'))['ledger']
            if previous_path.parent == directory and previous_path.exists():
                old = json.loads(previous_path.read_text(encoding='utf-8'))
                # A previous day's ledger is historical evidence, not today's
                # battle state. Guild work may have switched every character.
                if resumable_today(old, today):
                    path = previous_path
        record = (json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
            'date': today, 'status': '运行中', 'dungeon': '火麒麟十层',
            'groups': [{'members': list(group), 'target': 15, 'completed': 0, 'rounds': []}
                       for group in GROUPS]})
        resume_updated_at = record.get('updated_at', '')
        players = []
        team_infos = []
        guarded_devices = []
        group_index = None
        stage = '准备'

        def save():
            record['updated_at'] = datetime.now().isoformat(timespec='seconds')
            atomic_json_write(path, record)
            atomic_json_write(pointer, {'ledger': path.name})

        if record.get('status') in ('完成', '完成（有失败）'):
            self.config.model.grouped_awakening.scheduler.enable = False
            self.config.save()
            logger.info('今天四组已完成，保留完成记录，不重复运行')
            raise TaskEnd('GroupedAwakening')

        try:
            if [g['members'] for g in record['groups']] != [list(g) for g in GROUPS]:
                raise GameStuckError('已有分组记录与当前名单不符，停止以免重复刷')
            selection = getattr(self.config.model.guild_quick_participation, 'guild_accounts', None)
            if selection is None:
                raw = json.loads(Path('config', self.config.config_name + '.json').read_text(encoding='utf-8'))
                selection = raw.get('guild_quick_participation', {}).get('guild_accounts', {})
                chars = selection.get('characters', '\n'.join(SUPPORT_CHARACTERS))
                server = selection.get('server', SERVER)
            else:
                chars, server = selection.characters, selection.server
            accounts = resolve_accounts(self.config.find_jade.sup_account_list, chars, server)

            # The earlier 003/002/001 batch is reusable only with its complete
            # same-day, exact-account, 15-round record and explicit selection.
            settings = self.config.model.grouped_awakening
            if settings.options.credit_previous and record['groups'][0]['completed'] == 0:
                evidence = Path('log/TripleAwakening/oas_leveling/2026-11-01_154538.json')
                old = json.loads(evidence.read_text(encoding='utf-8'))
                if (today != '2026-11-01' or old.get('status') != '完成' or old.get('completed') != 15
                        or list(old.get('accounts', {}).values()) != list(GROUPS[0])
                        or [r['round'] for r in old.get('rounds', [])] != list(range(1,16))):
                    raise GameStuckError('无法核实首组先前15场的完成记录')
                record['groups'][0].update(completed=15, rounds=old['rounds'],
                                            credited_from=str(evidence))
                save()

            inventory = json.loads(subprocess.check_output(
                [str(MANAGER), 'info', '-v', 'all'], creationflags=subprocess.CREATE_NO_WINDOW))
            # Post-guild work needs only the primary window once all teams
            # have finished; do not require the two battle-only emulators.
            needed_windows = WINDOWS if any(g['completed'] < 15 and g.get('status') != '失败' for g in record['groups']) else WINDOWS[:1]
            for index, title in enumerate(needed_windows):
                matches = [v for v in inventory.values() if v.get('name') == title]
                if len(matches) != 1 or not matches[0].get('is_android_started'):
                    raise GameStuckError(title + ' 未开机或名称重复')
                keep_team_window_on_screen(title)
                info = matches[0]
                team_infos.append(info)
                conf = object.__new__(type(self.config))
                conf.__dict__.update(self.config.__dict__)
                conf.model = self.config.model.model_copy(deep=True)
                device_settings = conf.model.script.device
                device_settings.handle = title
                device_settings.serial = f"{info['adb_host_ip']}:{info['adb_port']}"
                args = psutil.Process(info['pid']).cmdline()
                device_settings.emulatorinfo_name = args[args.index('--vm') + 1]
                device_settings.screenshot_method = 'window_background'
                device_settings.control_method = 'window_message'
                device_settings.adb_restart = False
                device_settings.emulator_window_minimize = False
                conf.model.evo_zone.evo_zone_config.kirin_type = KirinType.FIREKIRIN
                conf.model.evo_zone.evo_zone_config.layer = Layer.TEN
                device = self.device if index == 0 else TeamDevice(conf, info)
                guarded_devices.append((device, install_login_expiry_guard(device, title)))
                players.append(Participant(conf, device))
            record['status'] = '运行中'
            record.pop('failure', None)
            record['notification_sent'] = False
            save()

            for group_index, group in enumerate(GROUPS):
                entry = record['groups'][group_index]
                # A final save can fail after every settlement was persisted.
                # Consume that exact durable evidence before any page actions;
                # it does not require an identity visible on a battle screen.
                if finalize_settled_round(entry, WINDOWS[:len(group)],
                                          datetime.now().isoformat(timespec='seconds')):
                    save()
                    logger.info('已按全队胜利及结算记录恢复第%s组第%s场',
                                group_index + 1, entry['completed'])
                if entry['completed'] >= 15 or entry.get('status') == '失败':
                    continue
                active = players[:len(group)]
                resumed_battle = bool(entry.get('battle_in_progress'))
                if resumed_battle:
                    # PID/window identity is insufficient after another task
                    # switches accounts on the same running emulator.
                    guild_path = Path('log/GuildQuickParticipation/oas_leveling') / (today + '.json')
                    if guild_path.exists():
                        guild = json.loads(guild_path.read_text(encoding='utf-8'))
                        if guild_changed_after_record(guild, resume_updated_at):
                            raise GameStuckError('战斗中断后寮活切换过账号，保留现场并要求核实，禁止按旧绑定恢复')
                # Prepare the extra windows first. They can still hold the
                # account most recently used by the primary guild worker.
                # Switching the primary window first can evict that stale
                # session before its account has been changed.
                indexes = range(len(group)) if resumed_battle else reversed(range(len(group)))
                for index in indexes:
                    name = group[index]
                    participant = active[index]
                    participant.expected_name = name
                    stage = f'第{group_index+1}组切换 {name}'
                    participant.step(stage, 300)
                    participant.device.stuck_record_clear()
                    if resumed_battle:
                        pid = psutil.Process(team_infos[index]['pid'])
                        binding = {'pid':pid.pid, 'started':pid.create_time(),
                                   'window':WINDOWS[index], 'character':name}
                        if entry.get('bindings', {}).get(WINDOWS[index]) != binding:
                            raise GameStuckError('中断后模拟器或角色绑定变化，无法安全恢复：' + name)
                        # A live PID does not prove that the character has not
                        # changed. Do not navigate or click while checking.
                        reader=RuleOcr(roi=(125,25,150,32),area=(125,25,150,32),
                                       mode='Single',method='Default',keyword='',name='group_resume_identity')
                        observed=[]
                        for _ in range(2):
                            participant.screenshot()
                            observed.append(reader.ocr(participant.device.image).strip().replace(' ',''))
                        if observed != [name,name]:
                            raise GameStuckError('中断后无法只读核实当前角色，保留战斗记录：' + name)
                        continue
                    # A user may pause while an account switch is showing the
                    # login page or the server-selection overlay. Close only a
                    # positively identified overlay, then let the existing
                    # account switcher choose the requested account.
                    # Only during pre-battle setup: the emulator may be
                    # running while its game client is on the Android launcher.
                    # Start the bound game, never the emulator, before reading
                    # a courtyard identity or trying to leave a team room.
                    if not participant.device.app_is_running():
                        from module.device.app_control import AppControl
                        logger.warning('%s game client is not foreground; starting only the bound game', WINDOWS[index])
                        AppControl.app_start(participant.device)
                        time.sleep(12)
                    try:
                        participant.screenshot()
                    except GameSessionExpiredError:
                        # The dialog was confirmed by Participant.screenshot.
                        # Recover only during pre-battle account setup, then
                        # switch to the assigned account and verify it below.
                        from tasks.Restart.login import LoginHandler
                        logger.warning('%s had a stale session; relogin before assigning %s', WINDOWS[index], name)
                        participant.step(stage + '恢复登录', 300)
                        try:
                            LoginHandler(config=participant.config, device=participant.device)._app_handle_login()
                        except GameBlackScreenError:
                            restart_black_screen_game(participant.device)
                            LoginHandler(config=participant.config, device=participant.device)._app_handle_login()
                        participant.step(stage, 300)
                        participant.screenshot()
                    # An interrupted switch may leave the SDK user center
                    # over the login screen. Close only this known overlay
                    # before attempting courtyard/name navigation.
                    if participant.appear(SwitchAccountAssets.I_SA_SWITCH_ACCOUNT_BTN):
                        switcher = SwitchAccount(participant.config, participant.device, accounts[name])
                        switcher.ui_click_until_disappear(
                            switcher.C_SA_LOGIN_FORM_USER_CENTER_CLOSE_BTN,
                            interval=1, stop=switcher.I_SA_SWITCH_ACCOUNT_BTN)
                        participant.screenshot()
                    region = SwitchAccountAssets.O_SA_CHECK_SELECT_SVR.ocr_single(participant.device.image)
                    in_server_selection = '已有角色' in region.replace(' ', '')
                    if in_server_selection:
                        participant.device.click(1104, 110, control_name='group_close_server_selection')
                        time.sleep(1)
                        participant.screenshot()
                    try:
                        current = None if (in_server_selection or participant.appear(participant.I_CHECK_LOGIN_FORM)) else participant.nickname()
                    except GameNotRunningError:
                        # The game can be on its login page after the window
                        # was brought back from the Android launcher.
                        from tasks.Restart.login import LoginHandler
                        participant.step(stage + '恢复登录', 300)
                        try:
                            LoginHandler(config=participant.config, device=participant.device)._app_handle_login()
                        except GameBlackScreenError:
                            restart_black_screen_game(participant.device)
                            LoginHandler(config=participant.config, device=participant.device)._app_handle_login()
                        participant.step(stage, 300)
                        current = participant.nickname()
                    if current != name:
                        if not FindJadeTask.switch_support_account(participant, accounts[name]):
                            raise GameStuckError('切号失败：' + name)
                        participant.step(stage + '后核对角色', 90)
                        if participant.nickname() != name:
                            raise GameStuckError('切号后角色不符：' + name)
                    entry.setdefault('verified', {})[WINDOWS[index]] = name
                    pid = psutil.Process(team_infos[index]['pid'])
                    entry.setdefault('bindings', {})[WINDOWS[index]] = {
                        'pid':pid.pid, 'started':pid.create_time(),
                        'window':WINDOWS[index], 'character':name}
                    save()
                if not resumed_battle:
                    # A later login can evict an earlier one. Recheck every
                    # identity after all switches and before any invitation.
                    for verification_pass in range(2):
                        retry_verification = False
                        for index, name in enumerate(group):
                            participant = active[index]
                            participant.step('组队前复核 ' + name, 120)
                            try:
                                observed = participant.nickname()
                            except GameSessionExpiredError:
                                if verification_pass:
                                    raise GameStuckError('组队前登录再次失效，停止重试：' + name)
                                logger.warning('组队前 %s 登录失效，恢复该窗口并重新核对全队', name)
                                from tasks.Restart.login import LoginHandler
                                participant.step('恢复登录 ' + name, 300)
                                LoginHandler(config=participant.config, device=participant.device)._app_handle_login()
                                participant.step('恢复后核对 ' + name, 120)
                                if participant.nickname() != name:
                                    if not FindJadeTask.switch_support_account(participant, accounts[name]):
                                        raise GameStuckError('恢复登录后切号失败：' + name)
                                    if participant.nickname() != name:
                                        raise GameStuckError('恢复登录后角色不符：' + name)
                                retry_verification = True
                                break
                            if observed != name:
                                raise GameStuckError('组队前角色不符：' + name)
                        if not retry_verification:
                            break
                # Keep physical bindings intact and use OASMain2 as captain.
                if group_index == 3:
                    active = [active[2], active[0], active[1]]
                leader = active[0]
                if not resumed_battle and entry['completed'] == 0 and 'assist_attempt' not in entry:
                    for participant in active:
                        participant.step('首场取消阵容锁定 ' + participant.expected_name, 180)
                        participant.screenshot()
                        if participant.appear(participant.I_CHECK_MAIN):
                            box = (243,100,933,211)
                            reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                                             keyword='', name='group_exploration_entry')
                            deadline = time.monotonic() + 20
                            last_click = 0
                            while time.monotonic() < deadline:
                                participant.screenshot()
                                if participant.appear(participant.I_CHECK_EXPLORATION):
                                    break
                                if participant.appear(participant.I_CHECK_MAIN) and time.monotonic()-last_click >= 3:
                                    rows = [r for r in reader.detect_and_ocr(participant.device.image)
                                            if r.ocr_text.replace(' ', '') == '探索']
                                    if len(rows) == 1:
                                        points = rows[0].box
                                        participant.device.click(int(box[0]+sum(float(p[0]) for p in points)/4),
                                                                 int(box[1]+sum(float(p[1]) for p in points)/4),
                                                                 control_name='group_exploration_entry')
                                        last_click = time.monotonic()
                                time.sleep(.3)
                            else:
                                raise GameStuckError('未能确认探索入口：' + participant.expected_name)
                        participant.ui_goto(page_awake_zones)
                        participant.evozone_enter()
                        if not participant.check_layer(Layer.TEN):
                            raise GameStuckError('未确认觉醒十层：' + participant.expected_name)
                        participant.check_lock(False)
                    leader.first_round_unlock = True
                for member in active[1:]:
                    member.leader_name = leader.expected_name
                invitation = InviteConfig(invite_number=InviteNumber.TWO if len(group)==3 else InviteNumber.ONE,
                                          friend_1=active[1].expected_name, friend_2=active[2].expected_name if len(group)==3 else '',
                                          default_invite=False)
                stage = f'第{group_index+1}组邀请队员'
                if resumed_battle:
                    if entry.get('battle_phase') != 'fighting':
                        raise GameStuckError('上次在点击挑战的瞬间中断，需确认当前场次后才能续跑')
                    if entry.get('active_round') != entry['completed']+1:
                        raise GameStuckError('中断前场次与完成次数不符，停止以免重复')
                    for participant in active:
                        participant.step('恢复中断的战斗与结算', 300)
                    try:
                        self.battle(active, entry['active_round']==15, entry, save)
                    except TeamBattleFailed:
                        entry.setdefault('failed_battles', []).append({
                            'round':entry['active_round'], 'recovered':True,
                            'time':datetime.now().isoformat(timespec='seconds')})
                        for key in ('pending_round','battle_in_progress','active_round','battle_phase'):
                            entry.pop(key, None)
                        entry['status'] = '失败'
                        entry['failure_reason'] = '战斗失败，按设置继续下一组'
                        save()
                        continue
                    entry['completed'] += 1
                    entry['rounds'].append({'round':entry['completed'], 'all_won':True,
                                            'recovered':True,
                                            'finished_at':datetime.now().isoformat(timespec='seconds')})
                    for key in ('pending_round','battle_in_progress','active_round','battle_phase'):
                        entry.pop(key, None)
                    save()
                    if entry['completed'] == 15:
                        continue
                else:
                    self.invite_with_refresh(active, invitation, record, save)
                for round_index in range(entry['completed'], 15):
                    for retry in range(1):
                        stage = f'第{group_index+1}组第{round_index+1}场组队'
                        self.wait_room(active)
                        for participant in active:
                            participant.step(stage + '战斗及结算', 300)
                        leader.screenshot()
                        # Require the necessary slots occupied before fighting.
                        if (not leader.is_in_room() or leader.appear(leader.I_ADD_1)
                                or (len(group)==3 and leader.appear(leader.I_ADD_2))):
                            raise GameStuckError('队伍人数未确认，禁止开始')
                        entry['battle_in_progress'] = True
                        entry['active_round'] = round_index+1
                        entry['battle_phase'] = 'starting'
                        save()
                        leader.click_fire()
                        entry['battle_phase'] = 'fighting'
                        save()
                        try:
                            self.battle(active, round_index==14, entry, save)
                            break
                        except TeamBattleFailed:
                            entry.setdefault('failed_battles', []).append({
                                'round':round_index+1, 'time':datetime.now().isoformat(timespec='seconds')})
                            for key in ('pending_round','battle_in_progress','active_round','battle_phase'):
                                entry.pop(key, None)
                            entry['status'] = '失败'
                            entry['failure_reason'] = '战斗失败，按设置继续下一组'
                            save()
                            break
                    if entry.get('status') == '失败':
                        logger.warning('第%s组战斗失败，保留 %s/15，继续下一组', group_index+1, entry['completed'])
                        break
                    entry['completed'] += 1
                    entry['rounds'].append({'round':round_index+1, 'all_won':True,
                                            'finished_at':datetime.now().isoformat(timespec='seconds')})
                    entry.pop('pending_round', None)
                    entry.pop('battle_in_progress', None)
                    entry.pop('active_round', None)
                    entry.pop('battle_phase', None)
                    save()
                    logger.info('分组觉醒：第%s组 %s/15，成员 %s',group_index+1,entry['completed'],group)
            stage = '觉醒后完成寮任务与捐赠'
            from tasks.GroupedAwakening.post_guild import finish_all
            finish_all(players[0], self.config)
            record['status'] = '完成（有失败）' if any(g.get('status') == '失败' for g in record['groups']) else '完成'
        except Exception as error:
            logger.exception(error)
            record['status'] = '出错'
            record['failure'] = {'group': None if group_index is None else group_index+1,
                                 'stage': stage, 'reason': str(error) or type(error).__name__}
            save()
            # Keep the scheduler alive and resume this activity later instead of
            # stopping the whole script on one failed group.
            scheduler = self.config.model.grouped_awakening.scheduler
            scheduler.next_run = datetime.now() + timedelta(minutes=10)
            scheduler.enable = True
            self.config.save()
            raise TaskEnd('分组觉醒本轮中断：'+str(error)+'，已安排十分钟后重试') from error
        finally:
            for device, original_screenshot in guarded_devices:
                device.screenshot = original_screenshot
            # Only a finished run disarms the schedule; an interrupted one stays
            # armed so the ten-minute retry above can actually happen.
            if record.get('status') in ('完成', '完成（有失败）'):
                self.config.model.grouped_awakening.scheduler.enable = False
            self.config.model.grouped_awakening.options.credit_previous = False
            self.config.save()
            save()
            settings = self.config.model.script.error
            if settings.notify_enable:
                try:
                    notifier = Notifier(settings.notify_config, True)
                    notifier.config_name = self.config.config_name.upper()
                    record['notification_sent'] = bool(notifier.push(
                        title='分组觉醒'+record['status'], content=json.dumps(record,ensure_ascii=False,indent=2)))
                except Exception as error:
                    record['notification_sent'] = False
                    record['notification_error'] = type(error).__name__
                save()
        raise TaskEnd('GroupedAwakening')
