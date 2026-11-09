"""Single controller for fire awakening floor ten, exactly fifteen team wins."""
import copy
from collections import deque
import cv2
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import psutil
from module.atom.ocr import RuleOcr
from module.exception import GameStuckError, ScriptEnd, TaskEnd
from module.logger import logger
from module.notify.notify import Notifier
from tasks.EvoZone.script_task import ScriptTask as EvoTask
from tasks.EvoZone.config import KirinType, Layer
from tasks.Component.GeneralInvite.config_invite import InviteConfig, InviteNumber
from tasks.GameUi.page import page_main, page_awake_zones
from tasks.TripleAwakening.device import TeamDevice


WINDOWS = ('MuMu安卓设备-1', 'MuMu安卓设备-1-1', 'MuMu安卓设备-1-2')
EXPECTED_NAMES = ('OASPlayer003', 'OASPlayer002', 'OASPlayer001')
MANAGER = Path('C:/Program Files/Netease/MuMu/nx_main/MuMuManager.exe')


class TeamBattleFailed(GameStuckError):
    pass


class Participant(EvoTask):
    def __init__(self, config, device, expected_name=None):
        super().__init__(config, device)
        # Device declares click history at class scope. Three active devices
        # must keep independent histories while retaining the click watchdog.
        device.click_record = deque(maxlen=15)
        self.expected_name = expected_name
        # Image rules store matched coordinates; never share them across devices.
        seen = set()
        for cls in type(self).__mro__:
            for name, rule in vars(cls).items():
                if name.startswith(('I_', 'C_', 'O_', 'L_')) and name not in seen:
                    # OCR rules cache a shared ONNX session after first use.
                    # It cannot be deep-copied; copy the rule's mutable state
                    # while retaining the existing shared inference model.
                    model = vars(rule).get('model') if isinstance(rule, RuleOcr) else None
                    memo = {id(model): model} if model is not None else {}
                    setattr(self, name, copy.deepcopy(rule, memo))
                    seen.add(name)
        self.deadline = time.monotonic() + 120
        self.stage = '准备'

    def screenshot(self):
        if time.monotonic() > self.deadline:
            raise GameStuckError(f'{self.device.config.script.device.handle}: {self.stage}超时')
        self.device.screenshot()
        self.handle_remote_login_dialog()
        self.handle_optional_engine_update()
        # Do not let generic cooperation invitation handling accept other teams.
        return self.device.image

    def step(self, name, timeout=90):
        self.stage = name
        self.deadline = time.monotonic() + timeout

    def failure_visible(self):
        box=(250,240,770,190)
        ocr=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',name='team_failure')
        text=''.join(r.ocr_text for r in ocr.detect_and_ocr(self.device.image)).replace(' ','')
        return '提升式神' in text and '提升阴阳师' in text and '再次挑战' in text

    def nickname(self):
        self.leave_existing_room()
        self.ui_get_current_page()
        self.ui_goto(page_main)
        rule = RuleOcr(roi=(110,20,225,45), area=(110,20,225,45),
                       mode='Full', method='Default', keyword='', name='triple_nickname')
        previous = ''
        deadline = min(self.deadline, time.monotonic() + 20)
        refreshed = False
        while time.monotonic() < deadline:
            self.screenshot()
            rows = [r.ocr_text.strip().replace(' ', '')
                    for r in rule.detect_and_ocr(self.device.image)]
            names = [name for name in rows if name and not name.isdigit()]
            name = names[0] if len(names) == 1 else ''
            if name and name == previous:
                return name
            previous = name
            if not name and not refreshed:
                self.device.refresh_handle_tree()
                refreshed = True
            time.sleep(.4)
        raise GameStuckError('无法稳定读取角色名，未发送邀请')

    def leave_existing_room(self):
        prompt = RuleOcr(roi=(400,270,480,110), area=(400,270,480,110),
                         mode='Full', method='Default', keyword='', name='triple_leave_prompt')
        last = 0
        while True:
            self.screenshot()
            if self.failure_visible():
                self.device.click(640,690,control_name='triple_close_failed_result')
                time.sleep(.5)
                continue
            if self.appear(self.I_REWARD) or self.appear(self.I_REWARD_GOLD):
                self.click(self.C_REWARD_1, interval=1)
                continue
            # Some material bags no longer match the generic reward template.
            reward_text = RuleOcr(roi=(450,655,380,60), area=(450,655,380,60),
                                  mode='Full', method='Default', keyword='', name='triple_reward_continue')
            reward_words=''.join(r.ocr_text for r in reward_text.detect_and_ocr(self.device.image)).replace(' ', '')
            if '点击屏幕继续' in reward_words:
                self.click(self.C_REWARD_1, interval=1)
                continue
            # The courtyard skin/story radial menu overlays the normal page
            # markers and can survive between tasks. Close only when multiple
            # distinct labels confirm that exact menu.
            menu = RuleOcr(roi=(470,190,350,300), area=(470,190,350,300),
                           mode='Full', method='Default', keyword='', name='triple_courtyard_menu')
            labels = ''.join(''.join(row.ocr_text.split()) for row in menu.detect_and_ocr(self.device.image))
            if ('换肤' in labels and '物语' in labels and ('忆梦' in labels or '绘卷' in labels)):
                self.device.click(850, 550, control_name='triple_close_courtyard_menu')
                time.sleep(.6)
                continue
            if self.appear(self.I_INVITE_ENSURE):
                box = (420,535,185,90)
                cancel = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                                 keyword='', name='triple_close_friend_list')
                rows = [r for r in cancel.detect_and_ocr(self.device.image)
                        if r.ocr_text.replace(' ', '') == '取消']
                if len(rows) != 1:
                    raise GameStuckError('无法确认好友列表取消按钮')
                if time.monotonic()-last > 2:
                    points=rows[0].box
                    self.device.click(int(box[0]+sum(float(p[0]) for p in points)/4),
                                      int(box[1]+sum(float(p[1]) for p in points)/4),
                                      control_name='triple_cancel_friend_list')
                    last=time.monotonic()
                continue
            text = ''.join(r.ocr_text for r in prompt.detect_and_ocr(self.device.image)).replace(' ', '')
            if '邀请队友继续' in text:
                if time.monotonic()-last > 2:
                    self.device.click(525,438,control_name='triple_cancel_continue_before_resume')
                    last=time.monotonic()
                continue
            if '确认退出组队面板' in text:
                if time.monotonic()-last > 2:
                    self.device.click(752,438,control_name='triple_leave_confirm')
                    last = time.monotonic()
                continue
            if not self.is_in_room(False):
                # The reward-to-confirm transition can briefly show neither
                # the room nor the next page. Do not hand an unknown frame to
                # navigation and miss the continue-invitation dialog.
                if any(self.appear(rule) for rule in (self.I_CHECK_MAIN, self.I_CHECK_AWAKE,
                       self.I_CHECK_EXPLORATION, self.I_CHECK_TEAM, self.I_FORM_TEAM, self.I_CHECK_RECORDS,
                       self.I_CHECK_LOGIN_FORM)):
                    return
                time.sleep(.3)
                continue
            if time.monotonic()-last > 2:
                self.appear_then_click(self.I_BACK_YELLOW, interval=2)
                last = time.monotonic()

    def detect_select(self, name=None):
        # Shared invite OCR uses fuzzy keywords, which can mistake OASPlayer for
        # OASPlayer001. Numeric suffixes must match exactly in this task.
        if not name:
            return False
        self.screenshot()
        matches = []
        for box in ((434,185,189,345), (729,184,196,346)):
            rule = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                           keyword='', name='triple_exact_friend')
            for row in rule.detect_and_ocr(self.device.image):
                if row.ocr_text.replace(' ', '') == name:
                    x = box[0] + sum(float(p[0]) for p in row.box)/4
                    y = box[1] + sum(float(p[1]) for p in row.box)/4
                    matches.append((int(x), int(y)))
        if len(matches) != 1:
            return False
        x,y = matches[0]
        self.I_SELECTED.roi_back = (x+90, y-45, 75, 75)
        self.device.click(*matches[0], control_name='triple_exact_friend')
        for _ in range(4):
            self.screenshot()
            if self.appear(self.I_SELECTED):
                return True
        raise GameStuckError('目标好友已点击，但未确认选中：' + name)


class ScriptTask(EvoTask):
    def run(self):
        if self.config.config_name != 'oas_leveling':
            raise ScriptEnd('三窗口觉醒仅支持 oas_leveling 配置')
        directory = Path('log/TripleAwakening/oas_leveling')
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (datetime.now().strftime('%Y-%m-%d_%H%M%S') + '.json')
        record = {'status':'运行中', 'dungeon':'火麒麟十层', 'target':15,
                  'completed':0, 'accounts':{}, 'rounds':[]}
        previous = sorted(directory.glob('*.json'), key=lambda p:p.stat().st_mtime)
        if previous:
            saved = json.loads(previous[-1].read_text(encoding='utf-8'))
            if (saved.get('status') != '完成' and 0 < saved.get('completed',0) < 15
                    and saved.get('accounts') == dict(zip(WINDOWS,EXPECTED_NAMES))):
                path = previous[-1]
                record = saved
                record['status'] = '运行中'
                record.pop('failure', None)
                record.pop('steps', None)
                record['notification_sent'] = False
        players = []

        def save():
            record['updated_at'] = datetime.now().isoformat(timespec='seconds')
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)

        try:
            # Read-only MuMu inventory: never start a VM or change its settings.
            inventory = json.loads(subprocess.check_output(
                [str(MANAGER), 'info', '-v', 'all'], creationflags=subprocess.CREATE_NO_WINDOW))
            for index, title in enumerate(WINDOWS):
                matches = [v for v in inventory.values() if v.get('name') == title]
                if len(matches) != 1 or not matches[0].get('is_android_started'):
                    raise GameStuckError(title + ' 未开机或名称重复')
                info = matches[0]
                # Config.__getattr__ delegates to model; copy.copy probes an
                # uninitialised instance and recurses before model exists.
                conf = object.__new__(type(self.config))
                conf.__dict__.update(self.config.__dict__)
                conf.model = self.config.model.model_copy(deep=True)
                settings = conf.model.script.device
                settings.handle = title
                settings.serial = f"{info['adb_host_ip']}:{info['adb_port']}"
                args = psutil.Process(info['pid']).cmdline()
                settings.emulatorinfo_name = args[args.index('--vm') + 1]
                settings.screenshot_method = 'window_background'
                settings.control_method = 'window_message'
                settings.adb_restart = False
                settings.emulator_window_minimize = False
                conf.model.evo_zone.evo_zone_config.kirin_type = KirinType.FIREKIRIN
                conf.model.evo_zone.evo_zone_config.layer = Layer.TEN
                device = self.device if index == 0 else TeamDevice(conf, info)
                participant = Participant(conf, device)
                participant.step('读取庭院角色名')
                name = participant.nickname()
                if name != EXPECTED_NAMES[index]:
                    raise GameStuckError(f'{title}: 期望 {EXPECTED_NAMES[index]}，识别为 {name}，未发邀请')
                record['accounts'][title] = name
                players.append(participant)
            if len(set(record['accounts'].values())) != 3:
                raise GameStuckError('三个窗口角色名重复或识别不清，停止组队')
            save()
            leader = players[0]
            names = list(record['accounts'].values())
            for p in players[1:]:
                p.leader_name = names[0]
            invitation = InviteConfig(invite_number=InviteNumber.TWO,
                                      friend_1=names[1], friend_2=names[2], default_invite=False)
            self.invite_with_refresh(players, invitation, record, save)
            for round_index in range(record['completed'], 15):
                self.wait_room(players, final=False)
                for p in players:
                    p.step(f'第{round_index+1}次战斗及结算', 300)
                leader.screenshot()
                if not leader.is_in_room() or leader.appear(leader.I_ADD_1) or leader.appear(leader.I_ADD_2):
                    raise GameStuckError('三人队伍未满，禁止开始挑战')
                leader.click_fire()
                self.battle(players, round_index == 14, record, save)
                record['completed'] += 1
                record['rounds'].append({'round':round_index+1, 'all_three_won':True,
                                         'finished_at':datetime.now().isoformat(timespec='seconds')})
                record.pop('pending_round', None)
                save()
                logger.info('三窗口火麒麟十层：%s/15，三人均完成结算', record['completed'])
            record['status'] = '完成'
        except Exception as error:
            logger.exception(error)
            record['status'] = '出错'
            record['failure'] = str(error)
            record['steps'] = {WINDOWS[i]: p.stage for i,p in enumerate(players)}
            save()
            raise ScriptEnd('三窗口觉醒停止：' + str(error)) from error
        finally:
            # Each explicit start authorizes one finite batch, including errors.
            self.config.model.triple_awakening.scheduler.enable = False
            self.config.save()
            save()
            settings = self.config.model.script.error
            if settings.notify_enable:
                try:
                    notifier = Notifier(settings.notify_config, True)
                    notifier.config_name = self.config.config_name.upper()
                    record['notification_sent'] = bool(notifier.push(
                        title='三人觉醒' + record['status'],
                        content=json.dumps(record, ensure_ascii=False, indent=2)))
                except Exception as error:
                    record['notification_sent'] = False
                    record['notification_error'] = type(error).__name__
                save()
        # A finite manual task: disable after success, no daily repeat.
        self.config.model.triple_awakening.scheduler.enable = False
        self.config.save()
        raise TaskEnd('TripleAwakening')

    @staticmethod
    def create_team(leader, invite_number=InviteNumber.TWO):
        leader.step('创建火麒麟十层私人房间', 180)
        # Other windows may have spent several minutes switching accounts;
        # the captain's previous login watchdog no longer describes this step.
        leader.device.stuck_record_clear()
        leader.screenshot()
        if leader.appear(leader.I_CHECK_MAIN):
            box=(243,100,933,211)
            reader=RuleOcr(roi=box,area=box,mode='Full',method='Default',
                           keyword='',name='team_exploration_entry')
            last=0
            while True:
                leader.screenshot()
                if leader.appear(leader.I_CHECK_EXPLORATION):
                    break
                if leader.appear(leader.I_CHECK_MAIN) and time.monotonic()-last >= 3:
                    rows=[r for r in reader.detect_and_ocr(leader.device.image)
                          if r.ocr_text.replace(' ', '') == '探索']
                    if len(rows)==1:
                        points=rows[0].box
                        leader.device.click(int(box[0]+sum(float(p[0]) for p in points)/4),
                                            int(box[1]+sum(float(p[1]) for p in points)/4),
                                            control_name='team_exploration_ocr')
                        last=time.monotonic()
                time.sleep(.3)
        leader.ui_get_current_page()
        leader.ui_goto(page_awake_zones)
        leader.evozone_enter()
        if not leader.check_layer(Layer.TEN):
            raise GameStuckError('未找到十层，停止创建房间')
        # MuMu's startup progress strip can hide the lower part of the
        # lock icon. Accept the visible upper part only with a strong match
        # to the locked template and a clearly worse unlocked match.
        leader.screenshot()
        area = leader.device.image[640:677, 680:750, :3]
        scores = []
        for name in ('lock', 'unlock'):
            template = cv2.cvtColor(cv2.imread(f'tasks/EvoZone/o/o_evozone_{name}.png'), cv2.COLOR_BGR2RGB)[:17]
            scores.append(cv2.minMaxLoc(cv2.matchTemplate(
                area, template, cv2.TM_CCOEFF_NORMED))[1])
        if getattr(leader, 'first_round_unlock', False):
            leader.check_lock(False)
        elif scores[0] >= 0.94 and scores[0] - scores[1] >= 0.2:
            logger.info('阵容锁定图标上半部已确认: %.3f', scores[0])
        else:
            leader.check_lock(True)
        while True:
            leader.screenshot()
            if leader.appear(leader.I_CHECK_TEAM):
                break
            leader.appear_then_click(leader.I_FORM_TEAM, interval=1)
        if not leader.create_room() or not leader.ensure_private() or not leader.create_ensure():
            raise GameStuckError('创建私人房间失败')
        if not leader.ensure_room_type(invite_number):
            raise GameStuckError('当前房间不支持所需人数')

    def invite_with_refresh(self, players, invitation, record, save):
        leader = players[0]
        for attempt in range(2):
            self.create_team(leader, invitation.invite_number)
            missing = None
            for friend in (name for name in (invitation.friend_1, invitation.friend_2) if name):
                if not leader.invite_friend(friend, invitation.find_mode):
                    missing = friend
                    break
            if missing is None:
                return
            if attempt:
                raise GameStuckError('退回庭院重新进入后仍未找到完整角色名：' + missing)
            # Revalidate both physical participant windows before refreshing the
            # leader's cached online list; a historical login is insufficient.
            for index,p in enumerate(players[1:], 1):
                p.step('重试前确认队员在线', 90)
                expected = p.expected_name or EXPECTED_NAMES[index]
                if not p.device.app_is_running() or p.nickname() != expected:
                    raise GameStuckError('无法确认队员仍在线：' + expected)
            record.setdefault('invitation_retries', []).append({
                'missing':missing, 'both_members_verified':True,
                'time':datetime.now().isoformat(timespec='seconds')})
            save()
            logger.info('两个队员在线，队长退回庭院重新进入一次：%s', missing)
            leader.step('刷新邀请列表：返回庭院', 120)
            if leader.nickname() != (leader.expected_name or EXPECTED_NAMES[0]):
                raise GameStuckError('队长返回庭院后角色名不匹配')

    @staticmethod
    def wait_room(players, final=False):
        for p in players:
            p.step('等待三人进入同一私人房间', 90)
        while True:
            ready = []
            for index,p in enumerate(players):
                p.screenshot()
                if index == 0:
                    prompt = RuleOcr(roi=(420,270,440,70), area=(420,270,440,70),
                                     mode='Full', method='Default', keyword='', name='triple_continue')
                    text=''.join(r.ocr_text for r in prompt.detect_and_ocr(p.device.image))
                    if '邀请队友继续' in text:
                        p.device.click(752,438,control_name='triple_continue_invitation')
                    else:
                        p.check_and_invite(False)
                else:
                    if p.appear(p.I_I_ACCEPT):
                        invite_ocr = RuleOcr(roi=(0,120,650,450), area=(0,120,650,450),
                                            mode='Full', method='Default', keyword='', name='triple_inviter')
                        text = ''.join(r.ocr_text for r in invite_ocr.detect_and_ocr(p.device.image)).replace(' ', '')
                        if p.leader_name not in text:
                            raise GameStuckError('邀请来源未确认是本队队长，停止接受')
                        if '觉醒业火轮拾层' not in text:
                            raise GameStuckError('邀请未确认是火麒麟十层：' + text)
                        p.check_then_accept()
                p.screenshot()
                ready.append(p.is_in_room())
            if all(ready):
                return
            time.sleep(.3)

    @staticmethod
    def battle(players, final, record, save):
        pending = record.get('pending_round', {})
        windows = [p.device.config.script.device.handle for p in players]
        won = [bool(pending.get('won', {}).get(w, False)) for w in windows]
        settled = [bool(pending.get('settled', {}).get(w, False)) for w in windows]
        exploration_frames = [0] * len(players)
        while not all(settled):
            for index,p in enumerate(players):
                if settled[index]:
                    continue
                p.screenshot()
                if p.appear(p.I_FALSE) or p.failure_visible():
                    raise TeamBattleFailed(windows[index] + ': 战斗失败')
                if p.handle_soul_mismatch_dialog():
                    continue
                if p.appear_then_click(p.I_PREPARE_HIGHLIGHT, interval=1):
                    continue
                if p.appear(p.I_WIN) or p.appear(p.I_DE_WIN):
                    won[index] = True
                    record['pending_round'] = {'round':record['completed']+1,
                                               'won':dict(zip(windows,won)),
                                               'settled':dict(zip(windows,settled))}
                    save()
                    p.click(p.C_WIN_1, interval=1)
                    continue
                if p.appear(p.I_REWARD) or p.appear(p.I_REWARD_GOLD):
                    p.click(p.C_REWARD_1, interval=1)
                    continue
                if won[index]:
                    reward_text = RuleOcr(roi=(450,655,380,60), area=(450,655,380,60),
                                          mode='Full', method='Default', keyword='', name='triple_reward_continue')
                    reward_words=''.join(r.ocr_text for r in reward_text.detect_and_ocr(p.device.image)).replace(' ', '')
                    if '点击屏幕继续' in reward_words:
                        p.click(p.C_REWARD_1, interval=1)
                        continue
                continue_visible=False
                if won[index] and index == 0:
                    prompt = RuleOcr(roi=(420,270,440,70), area=(420,270,440,70),
                                     mode='Full', method='Default', keyword='', name='triple_settlement_continue')
                    text=''.join(r.ocr_text for r in prompt.detect_and_ocr(p.device.image))
                    continue_visible='邀请队友继续' in text
                returned=False
                if won[index] and p.is_in_room():
                    room_ocr=RuleOcr(roi=(80,0,270,90),area=(80,0,270,90),mode='Full',
                                     method='Default',keyword='',name='triple_room_confirm')
                    returned='协战队伍' in ''.join(r.ocr_text for r in room_ocr.detect_and_ocr(p.device.image))
                if won[index] and index > 0 and (p.appear(p.I_GI_HOME) or p.appear(p.I_CHECK_MAIN)):
                    name_ocr=RuleOcr(roi=(125,25,150,32),area=(125,25,150,32),mode='Single',
                                     method='Default',keyword='',name='triple_settled_character')
                    returned=name_ocr.ocr(p.device.image).replace(' ','') == (p.expected_name or EXPECTED_NAMES[index])
                if won[index] and index > 0 and not returned:
                    exploration=RuleOcr(roi=(100,610,180,105),area=(100,610,180,105),
                                        mode='Full',method='Default',keyword='',name='triple_exploration_settled')
                    map_text=''.join(r.ocr_text for r in exploration.detect_and_ocr(p.device.image)).replace(' ','')
                    visible=p.appear(p.I_CHECK_EXPLORATION) and '觉醒材料' in map_text
                    exploration_frames[index]=exploration_frames[index]+1 if visible else 0
                    returned=exploration_frames[index]>=2
                if won[index] and (returned or continue_visible):
                    settled[index] = True
                    record['pending_round'] = {'round':record['completed']+1,
                                               'won':dict(zip(windows,won)),
                                               'settled':dict(zip(windows,settled))}
                    save()
                    if final and continue_visible:
                        p.device.click(525,438,control_name='triple_finish_cancel_invitation')
                    elif final and p.appear(p.I_GI_SURE):
                        p.appear_then_click(p.I_GI_CANCEL, interval=1)
            time.sleep(.2)
