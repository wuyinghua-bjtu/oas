"""Kirin participation and guild reward navigation from observed screens."""
from time import monotonic
from module.exception import GameStuckError
from module.atom.ocr import RuleOcr
from tasks.GuildQuickParticipation.reward import image, claim_reward

COURTYARD_GUILD=image('courtyard_guild',(552,615,58,63),(535,600,95,95))
GUILD_HUNT=image('guild_hunt',(12,250,93,31),(0,225,230,110))
GUILD_TASK=image('guild_collective',(12,159,98,31),(0,140,230,105))
HUNT_TITLE=image('hunt_title',(144,14,109,48),(125,0,145,80))
CHALLENGE=image('hunt_challenge',(1122,564,110,119),(1090,535,170,165))
PREPARE=image('hunt_prepare',(1111,523,142,137),(1088,500,180,175))
EXIT_TEXT=image('hunt_exit_text',(438,284,401,62),(425,270,430,90))
EXIT_CONFIRM=image('hunt_exit_confirm',(663,407,181,65),(650,395,210,90))
DEFEAT=image('hunt_defeat',(681,111,274,159),(660,90,310,200))
NO_ASSIST=image('hunt_no_assist',(438,283,407,62),(425,270,430,90))


def _transition(task, check, click, timeout=20, interrupt=None):
    deadline=monotonic()+timeout
    clicked=False
    while monotonic()<deadline:
        task.screenshot()
        if check():
            return
        if interrupt and interrupt():
            continue
        if not clicked and click():
            clicked=True
    raise GameStuckError('Guild activity transition was not confirmed')


def _words(task, box):
    rule = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                   keyword='', name='guild_navigation')
    return ''.join(row.ocr_text for row in rule.detect_and_ocr(task.device.image)).replace(' ', '')


def no_assist_dialog(task):
    if task.appear(NO_ASSIST):
        return True
    words = _words(task, (425,270,430,150))
    return ("未向寮友借用协战式神" in words
            and "是否继续挑战" in words)


def guild_activity_board(task):
    return ('集体任务' in _words(task, (140,150,230,80))
            and '狩猎战' in _words(task, (140,400,230,80)))


def guild_activity_home(task):
    return ((task.appear(GUILD_HUNT) and task.appear(GUILD_TASK))
            or guild_activity_board(task))


def hunt_defeat(task):
    if task.appear(DEFEAT):
        return True
    words = _words(task, (300,330,700,300))
    return ('提升自己战斗力' in words
            and '提升阴阳师' in words and '再次挑战' in words)


def open_guild(task, timeout=30):
    from time import sleep
    deadline = monotonic() + timeout
    next_click = 0
    clicks = 0
    while monotonic() < deadline:
        task.screenshot()
        if guild_activity_home(task):
            return
        if clicks >= 4 or monotonic() < next_click:
            sleep(.3)
            continue
        if task.appear(COURTYARD_GUILD):
            task.device.click(580,644,control_name='guild_open_from_courtyard')
        else:
            from tasks.CollectiveMissions.assets import CollectiveMissionsAssets as A
            if not task.appear(A.I_CM_SHRINE):
                sleep(.3)
                continue
            task.device.click(900,650,control_name='guild_open_shrine')
        clicks += 1
        next_click = monotonic() + 2
    raise GameStuckError('未确认阴阳寮神社活动入口（已有限重试）')


def kirin_and_reward(task, claim=True):
    """Enter and exit while preparing, then claim the ten guild-task rewards."""
    open_guild(task)
    def open_hunt():
        if guild_activity_board(task):
            task.device.click(260,500,control_name='guild_open_hunting_board')
            return True
        if task.appear(GUILD_HUNT):
            x,y,w,h=GUILD_HUNT.roi_front
            task.device.click(210,y+h//2+30,control_name='guild_open_hunting')
            return True
        return False
    _transition(task,lambda:task.appear(HUNT_TITLE) and task.appear(CHALLENGE),open_hunt)
    def challenge():
        if task.appear(CHALLENGE):
            task.device.click(1180,625,control_name='guild_hunt_challenge')
            return True
        return False
    assist_clicks = 0
    next_assist_click = 0
    def confirm_no_assist():
        nonlocal assist_clicks, next_assist_click
        if not no_assist_dialog(task):
            return False
        now = monotonic()
        if assist_clicks < 3 and now >= next_assist_click:
            task.device.click(752,438,control_name="guild_continue_without_assist")
            assist_clicks += 1
            next_assist_click = now + 2
        return True
    _transition(task,lambda:task.appear(PREPARE),challenge,timeout=35,interrupt=confirm_no_assist)
    return exit_prepare_and_claim(task, claim=claim)


def exit_prepare_and_claim(task, claim=True):
    """Continue an already-confirmed Kirin preparation screen."""
    def exit_preparation():
        if task.appear(PREPARE):
            task.device.click(37,33,control_name='guild_hunt_exit')
            return True
        return False
    task.screenshot()
    already_defeated = hunt_defeat(task)
    if not already_defeated:
        _transition(task,lambda:task.appear(EXIT_TEXT) and task.appear(EXIT_CONFIRM),exit_preparation)
    def confirm_exit():
        if task.appear(EXIT_TEXT) and task.appear(EXIT_CONFIRM):
            task.device.click(752,438,control_name='guild_hunt_confirm_exit')
            return True
        return False
    if not already_defeated:
        _transition(task,lambda:hunt_defeat(task),confirm_exit)
    def dismiss_defeat():
        if hunt_defeat(task):
            task.device.click(640,665,control_name='guild_hunt_defeat_close')
            return True
        return False
    _transition(task,lambda:task.appear(HUNT_TITLE),dismiss_defeat)
    def return_guild():
        if task.appear(HUNT_TITLE):
            task.device.click(44,37,control_name='guild_hunt_back')
            return True
        return False
    from tasks.CollectiveMissions.assets import CollectiveMissionsAssets as A
    _transition(task,lambda:guild_activity_home(task) or task.appear(A.I_CM_SHRINE),return_guild)
    if not guild_activity_home(task):
        open_guild(task)
    if not claim:
        return {'state': '待觉醒后领取'}
    from tasks.GuildQuickParticipation.reward import MISSION
    def open_tasks():
        if guild_activity_board(task):
            task.device.click(260,250,control_name='guild_open_collective_board')
            return True
        if task.appear(GUILD_TASK):
            x,y,w,h=GUILD_TASK.roi_front
            task.device.click(210,y+h//2+30,control_name='guild_open_collective_tasks')
            return True
        return False
    _transition(task,lambda:task.appear(MISSION),open_tasks)
    result=claim_reward(task)
    if result['state'] != 'claimed':
        raise GameStuckError('Guild activity completed but claimable task reward was not confirmed')
    return result


def leave_guild_after_reward(task, timeout=25):
    from tasks.GuildQuickParticipation.reward import MISSION, REWARD
    from tasks.CollectiveMissions.assets import CollectiveMissionsAssets as A
    from time import sleep
    deadline=monotonic()+timeout
    closed=False
    last_back=0
    backs=0
    while monotonic()<deadline:
        task.screenshot()
        if task.appear(COURTYARD_GUILD):
            return
        if task.appear(REWARD):
            continue
        if task.appear(MISSION):
            if not closed:
                task.device.click(1168,120,control_name='guild_tasks_back')
                closed=True
            continue
        if (task.appear(GUILD_TASK) or guild_activity_board(task)
                or task.appear(A.I_CM_SHRINE)) and backs<3 and monotonic()-last_back>=3:
            task.device.click(45,37,control_name='guild_return_courtyard')
            last_back=monotonic()
            backs+=1
            sleep(.5)
    raise GameStuckError('领奖后未能确认返回庭院')
