"""Run one authorized guardian round from the verified activity screen."""
from module.config.config import Config
from module.config.local_values import local_text
from tasks.Mentorship.device import BoundDevice, validate_profiles
from tasks.Mentorship.guard_remaining import read_remaining
from tasks.Mentorship.guardian_device import GuardianDevices
from tasks.Mentorship.battle_pair import PairBattle

mc, ac = Config('oas1'), Config('oas_leveling')
validate_profiles(mc, ac)
m, a = BoundDevice(mc), BoundDevice(ac)
remaining = read_remaining(m)
print('GUARD_REMAINING', remaining, flush=True)
if remaining is None or remaining <= 0:
    raise RuntimeError('守护历练剩余次数未确认')
pair = GuardianDevices(m, a, local_text('LOCAL_OCR_NAME03'))
if not pair.invite_and_lock():
    raise RuntimeError('守护历练邀请或双端阵容锁定失败')
print('PAIR_LOCKED', flush=True)
if not pair.start():
    raise RuntimeError('守护历练开战未确认')
print('BATTLE_STARTED', flush=True)
if not PairBattle(m, a).run(timeout=180, guardian=True):
    raise RuntimeError('守护历练双端结算未确认')
print('BOTH_BATTLES_COMPLETED', flush=True)
