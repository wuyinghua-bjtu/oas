"""Inspect switch recognition without changing any buff."""
import time
import cv2
import numpy as np
from module.config.config import Config
from tasks.Mentorship.device import BoundDevice
from tasks.Mentorship.buff_device import MasterBuffs, _RULES, _locate_row, _switch

d = BoundDevice(Config('oas1'))
buffs = MasterBuffs(d)
if not buffs._panel(True):
    raise RuntimeError('加成面板未打开')
try:
    for step in range(3):
        d.screenshot()
        for name in ('exp_50', 'exp_100'):
            area = _locate_row(d.image, _RULES[name])
            color = None
            if area:
                x, y, w, h = area
                roi = d.image[y:y+h, x:x+w]
                hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
                red = (((hsv[:,:,0] < 10) | (hsv[:,:,0] > 170)) & (hsv[:,:,1] > 120) & (hsv[:,:,2] > 90)).mean()
                yellow = ((hsv[:,:,0] >= 12) & (hsv[:,:,0] <= 35) & (hsv[:,:,1] > 120) & (hsv[:,:,2] > 120)).mean()
                color = (round(red, 3), round(yellow, 3))
            print('READ', step, name, area, _switch(d.image, area) if area else None, color, flush=True)
        if step < 2:
            d.swipe([580, 320], [530, 240], control_name='probe_buff_scroll')
            time.sleep(.5)
finally:
    if not buffs._panel(False):
        raise RuntimeError('加成面板未关闭')
