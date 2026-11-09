"""师徒双设备任务编排。各界面动作由已验证的设备适配器提供。"""
from datetime import date
from .plan import daily_plan


class VerificationError(RuntimeError):
    pass


def _require(ok, message):
    if not ok:
        raise VerificationError(message)


def execute_daily(adapter, settings, day=None):
    settings.validate()
    simulated_day = day is not None
    day = day or date.today()
    _require(adapter.validate_bindings(settings), '师徒设备绑定或登录状态无法确认')
    for activity in daily_plan(day):
        if activity.name == 'apprentice_souls':
            _require(adapter.apprentice_souls(activity.rounds), '徒弟御魂壹层未确认完成 15 场')
            continue
        if activity.name == 'tako' and (day if simulated_day else date.today()).weekday() >= 5:
            continue
        if activity.name == 'guard':
            remaining = adapter.guard_remaining()
            if type(remaining) is not int or not 0 <= remaining <= 5:
                raise VerificationError('无法确认守护历练剩余次数')
            initial_remaining = remaining
            while remaining:
                # A real settlement returned the apprentice to the courtyard;
                # require an explicit rejoin for every round.
                _require(adapter.guard_invite(settings.apprentice_name), '未确认徒弟接受守护邀请')
                _require(adapter.lock_both_lineups('guard'), '守护历练双方阵容未确认锁定')
                _require(adapter.guard_battle(), '守护历练战斗未确认完成')
                after = adapter.guard_remaining()
                _require(type(after) is int and 0 <= after < remaining,
                         '守护历练完成后未确认次数减少')
                remaining = after
            if initial_remaining:
                _require(adapter.guard_zero_confirmed(), '无法确认守护历练次数已用完')
            continue
        enabled = []
        try:
            for buff in activity.mentor_buffs:
                # Record intent before attempting the change so cleanup also
                # handles a timeout after the switch actually changed.
                enabled.append(buff)
                _require(adapter.set_mentor_buff(buff, True), f'无法确认开启师父加成 {buff}')
            for index in range(activity.rounds):
                _require(adapter.create_private_room(activity.name), f'{activity.name} 无法创建私人房间')
                _require(adapter.invite_and_verify(settings.apprentice_name, settings.apprentice_server),
                         f'{activity.name} 未确认指定徒弟入队')
                _require(adapter.lock_both_lineups(activity.name), f'{activity.name} 双方阵容未确认锁定')
                _require(adapter.start_battle(activity.name), f'{activity.name} 未确认双方进入战斗')
                if activity.mentor_exit_after_prepare:
                    _require(adapter.mentor_exit_after_prepare(), '石距师父退出未确认')
                _require(adapter.wait_battle_result(activity.name, activity.mentor_exit_after_prepare),
                         f'{activity.name} 第 {index + 1} 场未确认完成')
        finally:
            failures = []
            for buff in reversed(enabled):
                try:
                    if not adapter.set_mentor_buff(buff, False):
                        failures.append(buff)
                except Exception:
                    failures.append(buff)
            if failures:
                raise VerificationError('无法确认关闭师父加成：' + ', '.join(failures))
