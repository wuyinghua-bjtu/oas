"""Account selection and weekday policy for the independent guild task."""
from datetime import datetime, time, timedelta


SUPPORT_CHARACTERS = (
    'OASPlayer011', 'OASPlayer010', 'OASPlayer009', 'OASPlayer008',
    'OASPlayer007', 'OASPlayer002', 'OASPlayer006', 'OASPlayer005',
    'OASPlayer004', 'OASPlayer003', 'OASPlayer001',
)
SERVER = '砂狐乐园'

# One account must finish all requested stages before switching to the next.
ACCOUNT_STAGES = ('courtyard_affairs', 'friend_like_and_gift', 'guild_activity_enter_exit', 'claim_guild_task_reward')


def select_accounts(accounts, characters=None, server=SERVER):
    """Resolve the configured names against FindJade accounts, without guessing."""
    if characters is None:
        names = list(SUPPORT_CHARACTERS)
    else:
        names = [name.strip() for name in characters.replace('，', ',').replace(',', '\n').splitlines() if name.strip()]
    if not names:
        raise ValueError('小号寮活动角色名单不能为空')
    if len(names) != len(set(names)):
        raise ValueError('小号寮活动角色名单存在重复角色')
    chosen = []
    for name in names:
        matches = [account for account in accounts
                   if account.character == name and account.svr == server and account.is_valid()]
        if len(matches) != 1:
            raise ValueError(f'寻找协作的小号列表中，{server} 的 {name} 必须恰好有一个有效配置')
        chosen.append(matches[0])
    return chosen


def activity_for_day(day):
    return 'kirin' if day.weekday() <= 3 else 'netherworld'


def next_start(now, start=time(19, 0)):
    """Use the existing Hunt default of 19:00 as the proposed daily start."""
    today = datetime.combine(now.date(), start, tzinfo=now.tzinfo)
    return today if now < today else today + timedelta(days=1)
