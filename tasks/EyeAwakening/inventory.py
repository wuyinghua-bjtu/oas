"""Read visible synthesis-list rows without turning OCR gaps into zeroes."""
import re

import cv2
import numpy as np

from module.atom.ocr import RuleOcr


class InventoryUncertain(ValueError):
    pass


def _card_borders(image):
    # Gold card frames independently identify rows whose text OCR may miss.
    crop = image[145:650, 212:304, :3]
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (14, 100, 130), (40, 255, 255))
    ys = np.flatnonzero((mask > 0).sum(axis=1) >= 65)
    if not len(ys):
        return []
    runs = np.split(ys, np.where(np.diff(ys) > 1)[0] + 1)
    return [145 + int(round(float(run.mean()))) for run in runs]


def read_inventory_frame(image):
    """Return visible star counts; reject clipped or unreadable card rows."""
    box = (200, 145, 360, 505)
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default',
                     keyword='', name='eye_inventory_rows')
    rows = reader.detect_and_ocr(image)
    names, quantities = [], []
    stars = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6}
    for row in rows:
        text = re.sub(r'\s+', '', row.ocr_text or '')
        x, y = float(row.box[:, 0].mean()), float(row.box[:, 1].mean())
        if x < 100:
            continue
        name = re.fullmatch(r'([一二三四五六])星裂变之眼', text)
        amount = re.fullmatch(r'持有[:：](\d+)', text)
        if name:
            names.append((stars[name.group(1)], y + box[1]))
        elif amount:
            quantities.append((int(amount.group(1)), y + box[1]))
    if not names:
        raise InventoryUncertain('库存列表未识别到完整物品行')
    counts = {}
    for star, y in names:
        matches = [n for n, qty_y in quantities if 20 <= qty_y - y <= 65]
        if len(matches) != 1 or star in counts:
            raise InventoryUncertain(f'{star}星数量未能唯一识别')
        counts[star] = matches[0]
    if len(quantities) != len(names):
        raise InventoryUncertain('库存数量与名称行不一致')
    borders = _card_borders(image)
    def belongs(edge, y):
        offset = edge - y
        return -35 <= offset <= 15 or 50 <= offset <= 75

    if not borders or any(not any(belongs(edge, y) for _, y in names) for edge in borders):
        raise InventoryUncertain('物品图标与识别出的行不一致，可能有漏读或裁切')
    if any(not any(-35 <= edge - y <= 15 for edge in borders) for _, y in names):
        raise InventoryUncertain('物品名称缺少对应图标边框')
    return counts


def combine_boundaries(top, bottom):
    if not top or not bottom or list(top) != sorted(top) or list(bottom) != sorted(bottom):
        raise InventoryUncertain('库存列表内容或星级顺序无法确认')
    if any(star in bottom and bottom[star] != count for star, count in top.items()):
        raise InventoryUncertain('两次库存读取不一致')
    if not set(top).intersection(bottom):
        raise InventoryUncertain('首尾列表没有重叠，无法确认完整性')
    if min(top) > min(bottom) or max(top) > max(bottom):
        raise InventoryUncertain('列表首尾顺序不正确')
    counts = {**top, **bottom}
    return {5: counts.get(5, 0), 6: counts.get(6, 0)}
