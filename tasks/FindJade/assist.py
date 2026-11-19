"""Verify friend assist once per refresh period and support character."""
import json
import time
from pathlib import Path
from datetime import datetime

from module.logger import logger
from tasks.FindJade.report import current_period, CooperationReport
from tasks.GroupedAwakening.ledger import atomic_json_write


def ensure_sender_assist(task, timeout=30):
    # Same cycle definition as FindJade: 05:00 / 18:00, not each invocation.
    period = current_period(datetime.now())
    if period != task.cooperation_report.period:
        from module.exception import GameStuckError
        raise GameStuckError('协作周期已变化，停止旧周期首次协战准备')
    path = task.cooperation_report.directory / (
        'assist-' + period.strftime('%Y%m%d-%H%M') + '.json')
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'period': period.isoformat(), 'accounts': {}}
    if data.get('period') != period.isoformat():
        raise ValueError('Unexpected assist refresh period')
    key = CooperationReport.account_key(task.support_account)
    cached = data['accounts'].get(key, {})
    if cached.get('verified') is True or cached.get('attempted') is True:
        logger.info('本周期 %s 已尝试协战，跳过重复检测', task.support_account.character)
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task.screenshot()
        if task.is_in_real_battle(False) or task.battle_result_visible():
            task.device.save_screenshot(genre='findjade_assist_missed_preparation', interval=0)
            data['accounts'][key] = {'verified': False, 'attempted': True,
                                     'result': '准备已错过，继续当前战斗及结算',
                                     'checked_at': datetime.now().isoformat(timespec='seconds')}
            atomic_json_write(path, data)
            logger.warning('首次协战准备已错过，交由战斗控制器继续战斗及结算；不切号、不视为战败')
            return
        if task.appear(task.I_PREPARE_HIGHLIGHT):
            break
        time.sleep(.2)
    else:
        from module.exception import GameStuckError
        raise GameStuckError('首次协战准备页未确认，需要恢复当前任务，不视为战败')
    # Reuse the proven grouped-awakening card/marker recognition and drag
    # verification. This helper never clicks Ready or changes emulator state.
    from tasks.GroupedAwakening.script_task import ScriptTask as GroupTask
    task.expected_name = task.support_account.character
    evidence = {}
    GroupTask.prepare_assists([task], evidence, lambda: None, timeout=25)
    result = evidence.get('assist_attempt', {}).get(task.expected_name, '未确认')
    verified = evidence.get('assist_verified', {}).get(task.expected_name) is True
    data['accounts'][key] = {'verified': verified, 'attempted': True, 'result': result,
                              'checked_at': datetime.now().isoformat(timespec='seconds')}
    atomic_json_write(path, data)
    if not verified:
        logger.warning('首次好友协战未上阵确认：%s；按设置继续协作，不视为战败', result)
        return
    logger.info('本周期首次协战已上阵确认：%s', task.expected_name)


def prepare_exploration_assist_entry(task):
    """Disable the observed fixed-lineup switch before the first assist check."""
    period = task.cooperation_report.period
    path = task.cooperation_report.directory / ('assist-' + period.strftime('%Y%m%d-%H%M') + '.json')
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'accounts': {}}
    key = CooperationReport.account_key(task.support_account)
    cached = data['accounts'].get(key, {})
    if cached.get('verified') is True or cached.get('attempted') is True:
        return
    from module.atom.ocr import RuleOcr
    import cv2
    import numpy as np
    # Observed enabled fixed-lineup icon, independent of the moving background.
    template = cv2.imdecode(np.fromfile(str(Path(__file__).parent / 'res' / 'fixed_lineup_enabled.png'), dtype=np.uint8), cv2.IMREAD_COLOR)
    reader = RuleOcr(roi=(920,640,140,60), area=(920,640,140,60), mode='Full', method='Default', keyword='', name='sender_fixed_lineup')
    for attempt in range(3):
        task.screenshot()
        words = ''.join(r.ocr_text for r in reader.detect_and_ocr(task.device.image))
        if '固定阵容' not in words:
            raise ValueError('探索固定阵容入口未确认')
        region = cv2.cvtColor(task.device.image[640:695,880:935,:3], cv2.COLOR_RGB2BGR)
        score = float(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED).max())
        if score < .75:
            logger.info('首次协战探索入口：固定阵容已解除')
            return
        task.device.click(908,668,control_name='sender_disable_fixed_lineup')
        time.sleep(.5)
    raise ValueError('探索固定阵容开关未能解除')


def sender_battle_before(self, buff, config, timeout=45):
    ensure_sender_assist(self)
    from tasks.Component.GeneralBattle.general_battle import GeneralBattle
    return GeneralBattle.battle_before(self, buff, config, timeout=timeout)
