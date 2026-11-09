"""Report each completed character through the configured OAS notifier."""
from module.logger import logger
from module.notify.notify import Notifier


def notify_completion(config, character, counts, account_email):
    settings = config.model.script.error
    if not settings.notify_enable:
        return 'disabled'
    def shown(star):
        value = counts.get(star)
        return '未识别' if value is None else str(value) + '个'
    email = (account_email or '').strip()
    local = email.split('@', 1)[0] if '@' in email else ''
    prefix = local[:4] if len(local) >= 4 else '邮箱前四位未配置'
    content = (f'账号：{character}（{prefix}）\n每日副本掉落：50/50\n'
               f'当前持有五星裂变之眼：{shown(5)}\n'
               f'当前持有六星裂变之眼：{shown(6)}')
    try:
        notifier = Notifier(settings.notify_config, True)
        notifier.config_name = config.config_name.upper()
        return 'accepted' if notifier.push(title='小号裂变之眼刷满', content=content) else 'failed'
    except Exception as error:
        logger.warning('Eye completion notification failed: %s', type(error).__name__)
        return 'failed'
