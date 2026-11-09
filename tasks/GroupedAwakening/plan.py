"""Resolve the guild accounts into stable, ordered awakening teams."""

GROUPS = (
    ('OASPlayer003', 'OASPlayer002', 'OASPlayer001'),
    ('OASPlayer004', 'OASPlayer005', 'OASPlayer006'),
    ('OASPlayer007', 'OASPlayer008', 'OASPlayer009'),
    ('OASPlayer010', 'OASPlayer011', 'OASMain2'),
)


def resolve_accounts(configured, characters, server):
    names = [v.strip() for v in characters.replace('，', ',').replace(',', '\n').splitlines() if v.strip()]
    required = [name for group in GROUPS for name in group]
    # OASMain2 participates in the fourth awakening group; the separate guild
    # activity can retain its existing eleven-character selection.
    expected_guild = set(required) - {'OASMain2'}
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
