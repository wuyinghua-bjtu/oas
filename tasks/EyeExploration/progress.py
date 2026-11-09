"""Read the event counter only after confirming its icon on a reward screen."""
import re
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from tasks.EyeAwakening.progress import ProgressUncertain

REWARD_EYE = RuleImage(roi_front=(1081, 3, 34, 36), roi_back=(1069, 0, 60, 45),
                       method='Template matching', threshold=0.8,
                       file='./tasks/EyeExploration/reward_eye.png')


def read_reward_quota(image):
    if not REWARD_EYE.match(image):
        raise ProgressUncertain('结算页面未确认裂变之眼图标')
    box = (1141, 4, 79, 35)
    text = RuleOcr(roi=box, area=box, mode='Single', method='Default',
                   keyword='', name='eye_explore_reward_quota').ocr(image) or ''
    match = re.fullmatch(r'\s*(\d{1,2})\s*/\s*(\d{1,2})\s*', text)
    if not match:
        raise ProgressUncertain(f'结算页掉落进度无法确认：{text}')
    current, total = map(int, match.groups())
    if total != 50 or not 0 <= current <= total:
        raise ProgressUncertain(f'结算页掉落进度不合理：{text}')
    return current, total
