"""Enter the observed Netherworld preparation screen, leave, and claim guild credit."""
from time import monotonic, sleep
from module.atom.ocr import RuleOcr
from module.exception import GameStuckError
from tasks.Hunt.assets import HuntAssets
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.GuildQuickParticipation.kirin import GUILD_TASK, EXIT_CONFIRM, open_guild, guild_activity_board, guild_activity_home
from tasks.GuildQuickParticipation.reward import MISSION, claim_reward


def words(task, box, name):
    rule=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',name=name)
    return ''.join(r.ocr_text for r in rule.detect_and_ocr(task.device.image)).replace(' ','')


def wait_step(task, name, done, act, timeout=30):
    deadline=monotonic()+timeout
    last=0
    while monotonic()<deadline:
        task.screenshot()
        if done():
            return
        if monotonic()-last>=2.5 and act():
            last=monotonic()
        sleep(.2)
    task.device.save_screenshot(genre='guild_netherworld_failure',interval=1)
    raise GameStuckError('阴界之门未确认步骤：'+name)


def click(task,x,y,name):
    task.device.click(x,y,control_name=name)
    return True


def title(task):
    if not task.appear(HuntAssets.I_NW_CHALLAGE):
        return False
    ranking = words(task, (600,100,630,400), 'guild_nether_rank')
    return sum(label in ranking for label in ('排行', '成员', '消灭轮数')) >= 2


def room(task):
    return '协战队伍' in words(task,(80,0,240,75),'guild_nether_room')


def prepared(task):
    return '准备' in words(task,(1100,510,170,180),'guild_nether_prepare')


def open_activity(task):
    if guild_activity_board(task):
        if '阴界之门' not in words(task,(140,400,230,80),'guild_nether_board_entry'):
            return False
        return click(task,260,500,'guild_nether_open_board')
    if not task.appear(GUILD_TASK):
        return False
    box=(0,130,245,410)
    rule=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',name='guild_nether_entry')
    matches=[r for r in rule.detect_and_ocr(task.device.image) if '阴界之门' in r.ocr_text.replace(' ','')]
    if len(matches)!=1:
        return False
    points=matches[0].box
    y=box[1]+sum(float(p[1]) for p in points)/len(points)
    return click(task,210,int(y+32),'guild_nether_open')


def netherworld_and_reward(task, claim=True):
    open_guild(task)
    wait_step(task,'进入活动地图',lambda:task.appear(HuntAssets.I_NW),
              lambda:open_activity(task))
    wait_step(task,'打开阴界之门',lambda:title(task),
              lambda:task.appear_then_click(HuntAssets.I_NW,interval=2))
    wait_step(task,'创建协战队伍',lambda:room(task),
              lambda:title(task) and task.appear_then_click(HuntAssets.I_NW_CHALLAGE,interval=2))
    wait_step(task,'进入准备',lambda:prepared(task),
              lambda:room(task) and click(task,1210,640,'guild_nether_challenge'))
    wait_step(task,'打开退出确认',lambda:'不消耗今日挑战次数' in words(task,(425,270,430,100),'guild_nether_exit'),
              lambda:prepared(task) and click(task,37,33,'guild_nether_leave'))
    def leave():
        if task.appear(EXIT_CONFIRM):
            return click(task,752,438,'guild_nether_confirm_exit')
        if task.appear(GeneralBattleAssets.I_FALSE):
            return click(task,640,690,'guild_nether_result_close')
        return False
    wait_step(task,'退出准备并关闭结算',lambda:task.appear(HuntAssets.I_NW),leave)
    wait_step(task,'返回阴阳寮',lambda:guild_activity_home(task),
              lambda:task.appear(HuntAssets.I_NW) and click(task,45,37,'guild_nether_map_back'))
    if not claim:
        return {'state': '待觉醒后领取'}
    def open_collective():
        if guild_activity_board(task):
            return click(task,260,250,'guild_nether_collective_board')
        return task.appear(GUILD_TASK) and click(task,210,208,'guild_nether_collective')
    wait_step(task,'打开集体任务',lambda:task.appear(MISSION),open_collective)
    result=claim_reward(task)
    if result['state']!='claimed':
        raise GameStuckError('阴界之门已退出，但未确认可领取集体任务奖励')
    return result
