"""Resolve the guild accounts into stable, ordered awakening teams."""
from module.config.local_values import local_text

GROUPS = (
    (local_text('LOCAL_SUPPORT_003'), local_text('LOCAL_SUPPORT_002'), local_text('LOCAL_SUPPORT_001')),
    (local_text('LOCAL_SUPPORT_004'), local_text('LOCAL_SUPPORT_005'), local_text('LOCAL_SUPPORT_006')),
    (local_text('LOCAL_SUPPORT_007'), local_text('LOCAL_SUPPORT_008'), local_text('LOCAL_SUPPORT_009')),
    (local_text('LOCAL_SUPPORT_010'), local_text('LOCAL_SUPPORT_011'), local_text('LOCAL_PARTNER2')),
)


def resolve_accounts(configured, characters, server):
    names = [v.strip() for v in characters.replace('，', ',').replace(',', '\n').splitlines() if v.strip()]
    required = [name for group in GROUPS for name in group]
    # The configured partner participates in the fourth awakening group; the separate guild
    # activity can retain its existing eleven-character selection.
    expected_guild = set(required) - {local_text('LOCAL_PARTNER2')}
    if len(names) != len(set(names)) or set(names) not in (expected_guild, set(required)):
        raise ValueError('寮任务名单与分组觉醒的原有角色不一致，请先核对名单')
    resolved = {}
    for name in required:
        matches = [account for account in configured
                   if account.character == name and account.svr == server and account.is_valid()
                   and account.account and account.apple_or_android]
        if len(matches) != 1:
            raise ValueError(f'{server} 的 {name} 必须恰好有一个有效小号配置')
        resolved[name] = matches[0]
    return resolved
