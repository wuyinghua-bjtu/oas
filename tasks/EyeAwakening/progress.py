"""Read the battle-drop quota, without confusing it with purchase quotas."""

import re
import cv2

from module.atom.ocr import RuleOcr
from module.atom.image import RuleImage


class ProgressUncertain(ValueError):
    pass


MAP_EYE = RuleImage(roi_front=(879, 10, 35, 36), roi_back=(865, 0, 60, 55),
                    method='Template matching', threshold=0.8,
                    file='./tasks/EyeAwakening/eye_map_icon.png')


def read_map_quota(image) -> tuple[int, int]:
    """Read the icon and unambiguous counter shown on the exploration map."""
    if not MAP_EYE.match(image):
        raise ProgressUncertain('探索界面未识别裂变之眼图标')
    box = (925, 0, 115, 60)
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                     keyword='', name='eye_map_quota')
    rows = reader.detect_and_ocr(image)
    candidates = [row.ocr_text for row in rows
                  if re.fullmatch(r'\s*\d{1,2}\s*/\s*\d{1,2}\s*', row.ocr_text)]
    if len(candidates) != 1:
        raise ProgressUncertain('探索界面掉落进度无法唯一识别')
    text = candidates[0]
    match = re.fullmatch(r'\s*(\d{1,2})\s*/\s*(\d{1,2})\s*', text)
    if not match:
        raise ProgressUncertain(f'探索界面掉落进度无法识别：{text}')
    current, total = map(int, match.groups())
    if total != 50 or not 0 <= current <= total:
        raise ProgressUncertain(f'探索界面掉落进度不合理：{text}')
    # This font's 7 is repeatedly read as 1, even on consecutive frames.
    # Cross-check only the positively identified activity tracker, enlarged
    # and contrast-adjusted; unrelated counters must never repair the quota.
    crop = image[200:320, 1000:1279, :3]
    if crop.size:
        crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        crop = cv2.convertScaleAbs(crop, alpha=1.5, beta=-60)
        roi = (0, 0, crop.shape[1], crop.shape[0])
        tracker = RuleOcr(roi=roi, area=roi, mode='Full', method='Default',
                          keyword='', name='eye_map_tracker_quota')
        text = ''.join(row.ocr_text for row in tracker.detect_and_ocr(crop))
        text = re.sub(r'\s+', '', text).replace('（', '(').replace('）', ')')
        if all(word in text for word in ('活动', '探索', '觉醒', '御魂', '契灵', '副本', '掉落')):
            matches = re.findall(r'掉落\(([0-9]{1,2})/50', text)
            if len(matches) == 1:
                sidebar = int(matches[0])
                if not 0 <= sidebar <= 50:
                    raise ProgressUncertain('活动追踪掉落进度超出范围')
                if sidebar != current:
                    if current == 1 and sidebar == 7:
                        current = sidebar
                    else:
                        raise ProgressUncertain(f'地图与活动追踪进度不一致：{current}/{sidebar}')
    return current, total


def parse_battle_quota(text: str) -> tuple[int, int]:
    text = re.sub(r'\s+', '', text or '').replace('（', '(').replace('）', ')')
    if not all(word in text for word in ('战斗', '探索', '觉醒', '御魂', '契灵', '掉落')):
        raise ProgressUncertain('未确认裂变之眼的战斗掉落说明')
    # The combat row contains exactly one progress counter; purchase rows are
    # never accepted as evidence, even when their counters also end in /50.
    matches = re.findall(r'\(?([0-9]{1,2})\s*/\s*([0-9]{1,2})\)?', text)
    if len(matches) != 1:
        raise ProgressUncertain('战斗掉落进度无法唯一识别')
    current, total = map(int, matches[0])
    if total != 50 or not 0 <= current <= total:
        raise ProgressUncertain('战斗掉落进度超出预期范围')
    return current, total


def read_battle_quota(image) -> tuple[int, int]:
    """Read the upper battle row of the positively identified source dialog."""
    header = RuleOcr(roi=(480, 92, 330, 55), area=(480, 92, 330, 55),
                     mode='Single', method='Default', keyword='', name='eye_source_title')
    title = (header.ocr(image) or '').replace(' ', '')
    if '裂变之眼获取途径' not in title:
        raise ProgressUncertain('未确认裂变之眼获取途径窗口')
    box = (365, 154, 450, 65)
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                     keyword='', name='eye_battle_quota')
    text = ''.join(row.ocr_text for row in reader.detect_and_ocr(image))
    return parse_battle_quota(text)


def read_queue_quota(image) -> tuple[int, int]:
    """Read the daily dungeon drop quota on the summon-queue dialog."""
    title_box = (420, 140, 400, 55)
    title = RuleOcr(roi=title_box, area=title_box, mode='Single',
                    method='Default', keyword='', name='eye_queue_title').ocr(image) or ''
    if '裂变之眼召唤队列' not in title.replace(' ', ''):
        raise ProgressUncertain('未确认裂变之眼召唤队列')
    box = (290, 505, 620, 42)
    text = RuleOcr(roi=box, area=box, mode='Single', method='Default',
                   keyword='', name='eye_queue_drop_quota').ocr(image) or ''
    text = re.sub(r'\s+', '', text).replace('（', '(').replace('）', ')')
    if not all(word in text for word in ('每日', '探索', '御魂', '契灵', '副本掉落')):
        raise ProgressUncertain('未确认队列中的每日副本掉落说明')
    matches = re.findall(r'\(([0-9]{1,2})/([0-9]{1,2})\)', text)
    if len(matches) != 1:
        raise ProgressUncertain('队列中的掉落进度无法唯一识别')
    current, total = map(int, matches[0])
    if total != 50 or not 0 <= current <= total:
        raise ProgressUncertain('队列中的掉落进度超出预期范围')
    return current, total


def read_drop_popup_quota(image) -> tuple[int, int]:
    """Read the explicit daily-drop popup shown on a qualifying reward."""
    box = (500, 345, 270, 35)
    label = RuleOcr(roi=box, area=box, mode='Single', method='Default',
                    keyword='', name='eye_drop_popup_label').ocr(image) or ''
    if '今日已获得裂变之眼' not in label.replace(' ', ''):
        raise ProgressUncertain('未确认裂变之眼掉落进度弹窗')
    box = (590, 387, 100, 37)
    current, remaining, total = RuleOcr(
        roi=box, area=box, mode='DigitCounter', method='Default',
        keyword='', name='eye_drop_popup_count').ocr(image)
    if total != 50 or not 0 <= current <= total or current + remaining != total:
        raise ProgressUncertain('掉落弹窗进度识别失败')
    return current, total
