"""Push results through the existing oas_leveling notification settings."""
from module.logger import logger
from module.notify.notify import Notifier


def notify_result(config, success, results, failure=None):
    """Submit a completion or failure report without exposing login credentials.

    Each result contains a character, a stage and a status. A failed push is
    returned to the caller so it can preserve the result locally.
    """
    settings = config.model.script.error
    if not settings.notify_enable:
        logger.warning('Guild task notification disabled in script settings')
        return False
    title = '小号寮活动完成' if success else '小号寮活动出错'
    lines = ['本轮结果：' + ('完成' if success else '未完成')]
    for result in results:
        lines.append(f"- {result['character']}｜{result['stage']}｜{result['status']}")
    if failure:
        lines.append('出错原因：' + failure)
    try:
        notifier = Notifier(settings.notify_config, True)
        notifier.config_name = config.config_name.upper()
        return bool(notifier.push(title=title, content='\n'.join(lines)))
    except Exception as error:
        logger.warning('Guild task notification failed: %s', type(error).__name__)
        return False
