"""Authorized single experience or gold battle with master-only buffs."""
import sys
from module.config.config import Config
from tasks.Mentorship.device import BoundDevice, validate_profiles
from tasks.Mentorship.buff_device import MasterBuffs
from tasks.Mentorship.normal_device import NormalDevices
from tasks.Mentorship.private_room import create_private_room
from tasks.Mentorship.battle_pair import PairBattle
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as Invite
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_team

mc, ac = Config('oas1'), Config('oas_leveling')
validate_profiles(mc, ac)
m, a = BoundDevice(mc), BoundDevice(ac)
ui, room = GameUi(mc, m), GeneralRoom(mc, m)
pair, buffs = NormalDevices(m, a, '冥界画师03'), MasterBuffs(m)
enabled, in_room, started = [], False, False
activity = sys.argv[1] if len(sys.argv) > 1 else 'experience'
if activity not in ('experience', 'gold'):
    raise ValueError('未知副本')
zone = '经验妖怪' if activity == 'experience' else '金币妖怪'
prefix = 'exp' if activity == 'experience' else 'gold'
try:
    for name in (prefix + '_50', prefix + '_100'):
        enabled.append(name)
        if not buffs.set(name, True):
            raise RuntimeError('未确认开启经验加成 ' + name)
        print('BUFF_ON', name, flush=True)
    if not ui.ui_goto_page(page_team, timeout=30):
        raise RuntimeError('无法到达组队界面')
    position = room.list_find(room.L_TEAM_LIST, zone, max_swipe=4)
    if not position:
        raise RuntimeError('找不到经验妖怪')
    m.click(*position, control_name='mentorship_experience_select')
    if not create_private_room(m, activity):
        raise RuntimeError('经验房间创建未确认')
    in_room = True
    if not pair.invite_and_join(activity) or not pair.pair_confirmed():
        raise RuntimeError('双端身份未确认')
    m.screenshot()
    if not Invite.I_FIRE.match(m.image):
        raise RuntimeError('师父挑战按钮未确认')
    m.click(*Invite.I_FIRE.coord(), control_name='mentorship_experience_start')
    started, in_room = True, False
    if not PairBattle(m, a).run(timeout=180):
        raise RuntimeError('未确认双方战斗完成')
    print('BOTH_BATTLES_COMPLETED', flush=True)
finally:
    if in_room:
        try:
            pair.leave_both()
        except Exception as exc:
            print('ROOM_CLEANUP_FAILED', str(exc), flush=True)
    if enabled:
        try:
            if not ui.ui_goto_page(page_main, timeout=30):
                raise RuntimeError('未回到庭院')
            failures = []
            for name in reversed(enabled):
                try:
                    if not buffs.set(name, False):
                        failures.append(name)
                    else:
                        print('BUFF_OFF', name, flush=True)
                except Exception:
                    failures.append(name)
            if failures:
                raise RuntimeError('未确认关闭加成 ' + ', '.join(failures))
        except Exception as exc:
            print('BUFF_CLEANUP_FAILED', str(exc), flush=True)
            raise
