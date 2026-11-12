"""Read the event counter only after confirming its icon on a reward screen."""
import re
import cv2
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from tasks.EyeAwakening.progress import ProgressUncertain


def read_drop_popup_quota(image):
    box = (500, 345, 270, 35)
    label = RuleOcr(roi=box, area=box, mode='Single', method='Default',
                    keyword='', name='eye_explore_popup_label').ocr(image) or ''
    if '今日已获得裂变之眼' not in label.replace(' ', ''):
        raise ProgressUncertain('未确认裂变之眼掉落进度弹窗')
    crop = image[0:45, 1120:1240, :3]
    crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    crop = cv2.convertScaleAbs(crop, alpha=1.5, beta=-60)
    box = (0, 0, crop.shape[1], crop.shape[0])
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                     keyword='', name='eye_explore_popup_enlarged')
    texts = [row.ocr_text for row in reader.detect_and_ocr(crop)]
    text = texts[0] if len(texts) == 1 else ''
    match = re.fullmatch(r'\s*(\d{1,2})\s*/\s*50\s*', text)
    if not match or not 0 <= int(match.group(1)) <= 50:
        raise ProgressUncertain('放大后的掉落弹窗进度无法确认')
    return int(match.group(1)), 50

REWARD_EYE = RuleImage(roi_front=(1081, 3, 34, 36), roi_back=(1069, 0, 60, 45),
                       method='Template matching', threshold=0.8,
                       file='./tasks/EyeExploration/reward_eye.png')


def read_reward_quota(image):
    if not REWARD_EYE.match(image):
        raise ProgressUncertain('结算页面未确认裂变之眼图标')
    crop = cv2.resize(image[0:45, 1120:1240, :3], None, fx=4, fy=4,
                      interpolation=cv2.INTER_CUBIC)
    box = (0, 0, crop.shape[1], crop.shape[0])
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                     keyword='', name='eye_explore_reward_quota')
    texts = [row.ocr_text for row in reader.detect_and_ocr(crop)]
    text = texts[0] if len(texts) == 1 else ''
    match = re.fullmatch(r'\s*(\d{1,2})\s*/\s*(\d{1,2})\s*', text)
    if not match:
        raise ProgressUncertain(f'结算页掉落进度无法确认：{text}')
    current, total = map(int, match.groups())
    if total != 50 or not 0 <= current <= total:
        raise ProgressUncertain(f'结算页掉落进度不合理：{text}')
    return current, total
