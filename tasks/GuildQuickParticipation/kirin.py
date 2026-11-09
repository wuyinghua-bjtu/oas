"""Kirin participation and guild reward navigation from observed screens."""
from time import monotonic
from module.exception import GameStuckError
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


def open_guild(task):
    def click():
        if task.appear(COURTYARD_GUILD):
            task.device.click(580,644,control_name='guild_open_from_courtyard')
            return True
        return False
    _transition(task,lambda:task.appear(GUILD_HUNT) and task.appear(GUILD_TASK),click)


def kirin_and_reward(task, claim=True):
    """Enter and exit while preparing, then claim the ten guild-task rewards."""
    open_guild(task)
    def open_hunt():
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
    confirmed_assist=[False]
    def confirm_no_assist():
        if not confirmed_assist[0] and task.appear(NO_ASSIST):
            task.device.click(752,438,control_name='guild_continue_without_assist')
            confirmed_assist[0]=True
            return True
        return False
    _transition(task,lambda:task.appear(PREPARE),challenge,timeout=35,interrupt=confirm_no_assist)
    return exit_prepare_and_claim(task, claim=claim)


def exit_prepare_and_claim(task, claim=True):
    """Continue an already-confirmed Kirin preparation screen."""
    def exit_preparation():
        if task.appear(PREPARE):
            task.device.click(37,33,control_name='guild_hunt_exit')
            return True
        return False
    _transition(task,lambda:task.appear(EXIT_TEXT) and task.appear(EXIT_CONFIRM),exit_preparation)
    def confirm_exit():
        if task.appear(EXIT_TEXT) and task.appear(EXIT_CONFIRM):
            task.device.click(752,438,control_name='guild_hunt_confirm_exit')
            return True
        return False
    _transition(task,lambda:task.appear(DEFEAT),confirm_exit)
    def dismiss_defeat():
        if task.appear(DEFEAT):
            task.device.click(640,300,control_name='guild_hunt_defeat_close')
            return True
        return False
    _transition(task,lambda:task.appear(HUNT_TITLE),dismiss_defeat)
    def return_guild():
        if task.appear(HUNT_TITLE):
            task.device.click(44,37,control_name='guild_hunt_back')
            return True
        return False
    _transition(task,lambda:task.appear(GUILD_HUNT) and task.appear(GUILD_TASK),return_guild)
    if not claim:
        return {'state': '待觉醒后领取'}
    from tasks.GuildQuickParticipation.reward import MISSION
    def open_tasks():
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
        if task.appear(GUILD_TASK) and backs<3 and monotonic()-last_back>=3:
            task.device.click(45,37,control_name='guild_return_courtyard')
            last_back=monotonic()
            backs+=1
            sleep(.5)
    raise GameStuckError('领奖后未能确认返回庭院')
