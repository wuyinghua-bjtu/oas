from pydantic import Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.SwitchAccount.switch_account_config import AccountInfo
from tasks.Component.config_scheduler import Scheduler


def resolve_eye_accounts(eye):
    """Use task-local slots in order; never guess or load another task's accounts."""
    accounts = []
    identities = set()
    for index in range(1, 5):
        account = getattr(eye, f'eye_account_{index}')
        if not any((account.character, account.svr, account.account, account.account_alias)):
            continue
        if not all(value.strip() for value in (account.character, account.svr, account.account)):
            raise ValueError(f'第{index}个小号必须填写角色名、服务器和登录账号')
        identity = (account.svr.strip(), account.character.strip())
        if any(name == identity[1] for _, name in identities):
            raise ValueError(f'第{index}个小号角色名重复，请使用不同角色名以区分进度')
        identities.add(identity)
        accounts.append(account.model_copy(update={'character': identity[1], 'svr': identity[0],
                                                   'account': account.account.strip()}))
    if not accounts:
        raise ValueError('请在裂变之眼任务中至少配置一个小号')
    return accounts


class EyeAwakeningOptions(ConfigBase):
    max_battles_per_account: int = Field(default=300, ge=1, le=1000,
                                         description='每个账号最多战斗次数，达到后停止并保留进度')


class EyeAwakening(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    options: EyeAwakeningOptions = Field(default_factory=EyeAwakeningOptions)
    eye_account_1: AccountInfo = Field(default_factory=AccountInfo)
    eye_account_2: AccountInfo = Field(default_factory=AccountInfo)
    eye_account_3: AccountInfo = Field(default_factory=AccountInfo)
    eye_account_4: AccountInfo = Field(default_factory=AccountInfo)
