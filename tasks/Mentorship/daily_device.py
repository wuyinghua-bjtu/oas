"""Device workflow for verified guardian, experience, and gold activities.

Stone remains deliberately unavailable until its different room and exit
screens can be checked on a weekday. This module is not an OASX entry point.
"""
from datetime import date
import time
from module.atom.ocr import RuleOcr

from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_team, page_shikigami_records
from tasks.WantedQuests.script_task import ScriptTask as SoulTask
from .battle_pair import PairBattle
from .buff_device import MasterBuffs
from .guard_remaining import read_remaining
from .guardian_device import GuardianDevices
from .navigation import go_activity_menu, leave_activity_menu, read_normal_remaining
from .normal_device import NormalDevices
from .private_room import create_private_room
from .apprentice_souls import run_apprentice_souls


def _require(value, message):
    if not value:
        raise RuntimeError(message)


def apply_mentor_soul_preset(config, device):
    """Apply the verified 师徒 preset in the first group before fighting."""
    task = SoulTask(config, device)
    task.ui_get_current_page()
    _require(task.ui_goto_page(page_shikigami_records, timeout=30), '无法打开师父式神录')
    task.click_preset()
    task.click(task.C_SOU_GROUP_1)
    time.sleep(1)
    device.swipe((720, 480), (720, 330), duration=.8, control_name='mentorship_reveal_preset')
    time.sleep(1)
    reader = RuleOcr(roi=(560, 125, 290, 490), area=(560, 125, 290, 490),
                     mode='Full', method='Default', keyword='', name='mentorship_preset_name')
    device.screenshot()
    matches = [r for r in reader.detect_and_ocr(device.image) if ''.join(r.ocr_text.split()) == '师徒']
    _require(len(matches) == 1, '无法唯一确认师徒御魂预设')
    y = int(sum(p[1] for p in matches[0].box) / len(matches[0].box)) + 125
    _require(145 <= y <= 580, '师徒御魂预设被遮挡')
    device.click(992, y, control_name='mentorship_apply_preset')
    deadline = time.monotonic() + 12
    confirm = RuleOcr(roi=(405,270,470,90), area=(405,270,470,90), mode='Full',
                      method='Default', keyword='', name='mentorship_preset_confirmation')
    while time.monotonic() < deadline:
        device.screenshot()
        if task.preset_already_equipped():
            return True
        words = ''.join(r.ocr_text for r in confirm.detect_and_ocr(device.image))
        if '更换' in words and '预设御魂' in words:
            device.click(753,440,control_name='mentorship_confirm_preset')
            time.sleep(1)
            device.screenshot()
            _require(task.appear(task.I_SOU_TEAM_PRESENT), '御魂切换后界面未确认')
            return True
        time.sleep(.3)
    raise RuntimeError('无法确认师徒御魂预设已装备')


def run_verified_daily(config, mentor, apprentice, name, day=None, apprentice_config=None,
                       apprentice_server='砂狐乐园'):
    """Run the verified subset. Device ownership must be held by caller."""
    if not name.strip() or not apprentice_server.strip():
        raise RuntimeError('徒弟角色名和服务器不能为空')
    if apprentice_config is None or apprentice_config.config_name != 'oas_leveling':
        raise RuntimeError('未提供已验证的徒弟设备配置')
    day = day or date.today()
    apply_mentor_soul_preset(config, mentor)
    ui = GameUi(config, mentor)
    rooms = GeneralRoom(config, mentor)
    name_reader = RuleOcr(roi=(0, 0, 1280, 720), area=(0, 0, 1280, 720),
                          mode='Full', method='Default', keyword='', name='mentorship_names')
    def read_name(image):
        results = []
        for item in name_reader.detect_and_ocr(image):
            points = item.box
            x0, y0 = int(min(p[0] for p in points)), int(min(p[1] for p in points))
            x1, y1 = int(max(p[0] for p in points)), int(max(p[1] for p in points))
            results.append((item.ocr_text, (x0, y0, x1 - x0, y1 - y0)))
        return results
    pair = NormalDevices(mentor, apprentice, name, read_name=read_name)
    guardian = GuardianDevices(mentor, apprentice, name, read_name=read_name)
    buffs = MasterBuffs(mentor)

    _require(go_activity_menu(config, mentor), '未找到妖气探索')
    remaining = read_remaining(mentor)
    if remaining is None:
        raise RuntimeError('无法确认守护历练剩余次数')
    while remaining:
        _require(guardian.invite_and_lock(), '守护邀请或阵容锁定未确认')
        _require(guardian.start(), '守护开战未确认')
        _require(PairBattle(mentor, apprentice).run(timeout=180, guardian=True), '守护双端结算未确认')
        after = read_remaining(mentor)
        _require(type(after) is int and 0 <= after < remaining, '守护结算后次数未减少')
        remaining = after

    for activity, zone, prefix in (('experience', '经验妖怪', 'exp'), ('gold', '金币妖怪', 'gold')):
        count = read_normal_remaining(mentor, activity)
        if count is None:
            raise RuntimeError(f'{zone} 剩余次数未确认')
        while count:
            _require(leave_activity_menu(mentor), '无法退出妖气探索')
            enabled = []
            in_room = False
            try:
                _require(ui.ui_goto_page(page_main, timeout=30), '无法返回庭院开启加成')
                for buff in (prefix + '_50', prefix + '_100'):
                    enabled.append(buff)
                    _require(buffs.set(buff, True), f'未确认开启 {buff}')
                _require(ui.ui_goto_page(page_team, timeout=30), '无法打开组队')
                # A list OCR hit is not proof that its row became selected:
                # the viewport can shift while scrolling. Re-find the row and
                # confirm the selected page title before creating a room.
                selected = False
                for attempt in range(4):
                    position = rooms.list_find(rooms.L_TEAM_LIST, zone, max_swipe=6)
                    if not position:
                        continue
                    mentor.click(*position, control_name='mentorship_select_activity')
                    time.sleep(1)
                    mentor.screenshot()
                    title = ''.join(rooms.O_GR_ZONES_NAME.ocr(mentor.image).split())
                    if title == zone or (zone == '金币妖怪' and title.startswith('金币')):
                        selected = True
                        break
                _require(selected, f'未确认选中 {zone}')
                _require(create_private_room(mentor, activity), f'{zone} 房间未确认')
                in_room = True
                _require(pair.invite_and_join(activity) and pair.pair_confirmed(), '师徒双方身份未确认')
                mentor.screenshot()
                _require(Invite.I_FIRE.match(mentor.image), '挑战按钮未确认')
                mentor.click(*Invite.I_FIRE.coord(), control_name='mentorship_start')
                in_room = False
                _require(PairBattle(mentor, apprentice).run(timeout=180), f'{zone} 双端结算未确认')
            finally:
                room_error = None
                if in_room:
                    try:
                        pair.leave_both()
                    except Exception as exc:
                        room_error = exc
                failures = []
                if enabled:
                    if not ui.ui_goto_page(page_main, timeout=30):
                        raise RuntimeError('无法回庭院，未确认关闭师父加成')
                    for buff in reversed(enabled):
                        try:
                            if not buffs.set(buff, False):
                                failures.append(buff)
                        except Exception:
                            failures.append(buff)
                    if failures:
                        raise RuntimeError('未确认关闭师父加成：' + ', '.join(failures))
                if room_error:
                    raise RuntimeError('未确认退出师徒房间') from room_error
            _require(go_activity_menu(config, mentor), '无法回到妖气探索核对次数')
            after = read_normal_remaining(mentor, activity)
            _require(type(after) is int and 0 <= after < count, f'{zone} 完成后次数未减少')
            count = after

    if day.weekday() < 5:
        stone_counts = [RuleOcr(roi=(720,y,50,27), area=(720,y,50,27),
                                mode='DigitCounter', method='Default', keyword='',
                                name='mentorship_stone_remaining_' + str(y)) for y in (198, 222)]
        def read_stone_count(device):
            found = []
            for rule in stone_counts:
                count, _, total = rule.ocr(device.image)
                if total == 2 and 0 <= count <= 2:
                    found.append(count)
            return found[0] if found and len(set(found)) == 1 else None
        # The mentor exits before settlement, so the apprentice's counter is
        # authoritative; the mentor's own count is expected to stay unchanged.
        _require(go_activity_menu(apprentice_config, apprentice), '无法查看徒弟石距次数')
        apprentice.screenshot()
        current = read_stone_count(apprentice)
        time.sleep(.5)
        apprentice.screenshot()
        current2 = read_stone_count(apprentice)
        _require(current is not None and current == current2,
                 '石距剩余次数未确认')
        while current:
            _require(leave_activity_menu(mentor), '无法退出妖气探索')
            _require(ui.ui_goto_page(page_team, timeout=30), '无法打开石距组队')
            selected = False
            for _ in range(4):
                point = rooms.list_find(rooms.L_TEAM_LIST, '石距', max_swipe=6)
                if not point:
                    continue
                mentor.click(*point, control_name='mentorship_select_stone')
                time.sleep(1)
                mentor.screenshot()
                title = ''.join(rooms.O_GR_ZONES_NAME.ocr(mentor.image).split())
                if title.startswith('石距') and len(title) <= 3:
                    selected = True
                    break
            _require(selected, '未确认选中石距')
            _require(create_private_room(mentor, 'tako'), '石距房间未确认')
            in_room = True
            try:
                _require(pair.invite_and_join('tako') and pair.pair_confirmed(), '石距师徒身份未确认')
                mentor.screenshot()
                _require(Invite.I_FIRE.match(mentor.image), '石距挑战按钮未确认')
                mentor.click(*Invite.I_FIRE.coord(), control_name='mentorship_stone_start')
                in_room = False
                _require(PairBattle(mentor, apprentice).run(stone_leader_exit=True, timeout=240),
                         '石距师父退出或徒弟结算未确认')
            finally:
                if in_room:
                    pair.leave_both()
            _require(go_activity_menu(config, mentor), '师父无法返回妖气探索')
            _require(go_activity_menu(apprentice_config, apprentice), '无法返回核对徒弟石距次数')
            apprentice.screenshot()
            after = read_stone_count(apprentice)
            _require(after is not None and 0 <= after < current, '石距完成后次数未减少')
            current = after
    _require(run_apprentice_souls(apprentice_config, apprentice, day=day,
                                  character=name, server=apprentice_server) == 15,
             '徒弟御魂壹层未完成 15 场')
    return True
