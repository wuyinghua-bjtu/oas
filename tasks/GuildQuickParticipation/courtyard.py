"""Complete courtyard affairs for the currently verified support account."""
from time import monotonic, sleep
import re

from module.exception import GameStuckError
from module.logger import logger
from module.atom.ocr import RuleOcr
from tasks.GameUi.page import page_main
from tasks.GameUi.game_ui import GameUi
from tasks.Restart.login import LoginHandler
from tasks.GuildQuickParticipation.kirin import COURTYARD_GUILD


def return_from_courtyard_affairs(task, timeout=25):
    """Close the confirmed affairs page and verify the courtyard."""
    deadline=monotonic()+timeout
    last_back=float('-inf')
    fortune=RuleOcr(roi=(450,100,340,445),area=(450,100,340,445),mode='Full',
                    method='Default',keyword='',name='guild_courtyard_fortune')
    continue_reader=RuleOcr(roi=(470,660,350,55),area=(470,660,350,55),mode='Full',
                            method='Default',keyword='',name='guild_courtyard_reward_continue')
    claimed_reader=RuleOcr(roi=(275,15,260,75),area=(275,15,260,75),mode='Full',
                           method='Default',keyword='',name='guild_courtyard_claimed')
    while monotonic()<deadline:
        task.screenshot()
        claimed=''.join(item.ocr_text for item in claimed_reader.detect_and_ocr(task.device.image)).replace(' ','')
        if '领取成功' in claimed:
            task.device.click(640,690,control_name='guild_courtyard_claimed_close')
            sleep(.5)
            continue
        text=''.join(item.ocr_text for item in fortune.detect_and_ocr(task.device.image)).replace(' ','')
        if re.search(r'第\d+签', text):
            prompt=''.join(item.ocr_text for item in continue_reader.detect_and_ocr(task.device.image)).replace(' ','')
            if '点击屏幕继续' in prompt:
                task.device.click(1000,550,control_name='guild_courtyard_reward_close')
                sleep(.5)
                continue
        if '累计奖励' in text and '签' in text:
            task.device.click(870,108,control_name='guild_courtyard_fortune_close')
            sleep(.5)
            continue
        affairs_visible=task.appear(LoginHandler.I_PAGE)
        if not affairs_visible and (task.appear(COURTYARD_GUILD) or task.appear(task.I_CHECK_MAIN)):
            return True
        if affairs_visible and monotonic()-last_back>=3:
            task.device.click(43,37,control_name='guild_courtyard_back')
            last_back=monotonic()
        sleep(.3)
    task.device.save_screenshot(genre='guild_courtyard_return_unconfirmed',interval=1)
    return False


def complete_courtyard_affairs(config, device, timeout=90):
    """Use existing courtyard controls and require the no-tasks indicator.

    The caller must already have switched to and verified the intended account.
    A timeout or unrecognized page leaves the account unfinished.
    """
    handler = LoginHandler(config=config, device=device)
    navigation = GameUi(config=config, device=device)
    navigation.ui_get_current_page()
    navigation.ui_goto(page_main)
    if not handler.ui_click_multi_scale(handler.I_NOTE, handler.I_PAGE,
                                        timeout=5, scale_range=(0.8, 1.2)):
        raise GameStuckError('Courtyard affairs page could not be confirmed')
    deadline = monotonic() + timeout
    complete_clicks = 0
    daily_selected = False
    blocked_since = None
    blocked_reader = RuleOcr(roi=(900,105,215,125), area=(900,105,215,125),
                             mode='Full', method='Default', keyword='',
                             name='guild_courtyard_blocked')
    done_reader = RuleOcr(roi=(965,110,140,490),area=(965,110,140,490),
                          mode='Full',method='Default',keyword='',name='guild_courtyard_done')
    done_frames=0
    guild_reader=RuleOcr(roi=(300,110,805,125),area=(300,110,805,125),
                         mode='Full',method='Default',keyword='',name='guild_courtyard_manual_task')
    while monotonic() < deadline:
        handler.screenshot()
        if daily_selected and complete_clicks>=1:
            button=device.image[625:670,1135:1200,:3].astype('float32')
            disabled=(button.max(axis=2)-button.min(axis=2)).mean()<90
            if disabled:
                statuses=''.join(r.ocr_text for r in done_reader.detect_and_ocr(device.image)).replace('巴完成','已完成')
                done_frames=done_frames+1 if '前往' not in statuses and statuses.count('已完成')>=4 else 0
                if done_frames>=2:
                    logger.info('Courtyard affairs confirmed by completed rows and disabled completion button')
                    return {'complete':True,'reason':''}
            else:
                done_frames=0
        if handler.appear(handler.I_NO_TASKS):
            logger.info('Courtyard affairs: no completable tasks remain')
            return {'complete': True, 'reason': ''}
        if handler.appear_then_click(handler.I_HARVEST_SOUL_2, interval=1) or \
                handler.appear_then_click(handler.I_HARVEST_SOUL_3, interval=1):
            continue
        if handler.ui_reward_appear_click():
            continue
        if handler.appear_then_click(handler.I_UI_AWARD, interval=.5):
            continue
        if handler.appear_then_click(handler.I_CONFIRM, interval=1):
            continue
        if not daily_selected and handler.appear_then_click(handler.I_DAILY, interval=1):
            daily_selected = True
            continue
        if handler.appear_then_click(handler.I_SUCCESS_CLAIMED, interval=1):
            continue
        if handler.appear_then_click(handler.I_SKIP, interval=1):
            continue
        if handler.appear_then_click(handler.I_LOGIN_RED_CLOSE, interval=1):
            continue
        if complete_clicks>=3:
            remaining=''.join(r.ocr_text for r in guild_reader.detect_and_ocr(device.image)).replace(' ','')
            if '现世逢魔' in remaining and '完成' in remaining:
                return {'complete':False,'reason':'现世逢魔需额外操作，一键完成后已记录跳过'}
            if '前往' in remaining and '契灵' in remaining:
                return {'complete':False,'reason':'寮集体任务需要契灵战斗，按设置未执行'}
        if complete_clicks >= 3 and device.image[112:220,275:1100].mean() > 160:
            words = ''.join(x.ocr_text for x in blocked_reader.detect_and_ocr(device.image)).replace(' ', '')
            if '道具不足' in words and '无法提交' in words:
                if blocked_since is None:
                    blocked_since = monotonic()
                elif monotonic()-blocked_since >= 1.5:
                    logger.warning('Courtyard affairs: item shortage prevents guild task submission')
                    return {'complete': False, 'reason': '寮集体任务道具不足，无法提交'}
            else:
                blocked_since = None
        else:
            blocked_since = None
        if complete_clicks < 3 and handler.appear_then_click(handler.I_COMPLETE_TASKS, interval=2.3):
            complete_clicks += 1
    device.save_screenshot(genre='guild_courtyard_unconfirmed', interval=1)
    raise GameStuckError('Courtyard affairs completion could not be confirmed')
