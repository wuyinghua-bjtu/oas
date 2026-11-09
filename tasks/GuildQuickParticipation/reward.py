"""Recognize the observed 我爱我寮 reward; never infer success from a click."""
from time import monotonic
from module.atom.image import RuleImage
from module.exception import GameStuckError


def image(name, front, back):
    return RuleImage(roi_front=front, roi_back=back, method='Template matching',
                     threshold=.85, file='./tasks/GuildQuickParticipation/res/'+name+'.png')


MISSION = image('mission_title',(555,132,115,46),(545,122,135,66))
CLAIM = image('claim',(566,464,144,60),(556,454,164,80))
REWARD = image('reward',(516,205,246,70),(506,195,266,90))
PROGRESS = image('in_progress',(595,475,87,35),(585,465,107,55))


def claim_reward(task, timeout=20):
    deadline=monotonic()+timeout
    clicked=False
    reward_count=0
    last_click=0
    completed_frames=0
    while monotonic()<deadline:
        task.screenshot()
        now=monotonic()
        if task.appear(REWARD):
            completed_frames=0
            if now-last_click>=1:
                task.device.click(640,490,control_name='guild_close_reward')
                last_click=now
                reward_count+=1
            continue
        if not task.appear(MISSION):
            completed_frames=0
            continue
        if task.appear(CLAIM):
            completed_frames=0
            if not clicked:
                task.device.click(638,494,control_name='guild_claim_ten')
                clicked=True
                last_click=now
            continue
        if task.appear(PROGRESS):
            if clicked and (not reward_count or now-last_click<1.5):
                completed_frames=0
                continue
            completed_frames+=1
            if completed_frames>=2:
                return {'clicked':clicked,'reward_screens':reward_count,
                        'state':'claimed' if clicked else 'already_or_not_ready'}
    raise GameStuckError('Unable to confirm guild reward state; preserve account and screenshot')
