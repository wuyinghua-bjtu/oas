"""Bounded, verified master-only experience and gold buff switches."""
import time

import cv2

from tasks.Component.GeneralBuff.assets import GeneralBuffAssets as Buff


_RULES = {'exp_50': Buff.O_EXP_50, 'exp_100': Buff.O_EXP_100,
          'gold_50': Buff.O_GOLD_50, 'gold_100': Buff.O_GOLD_100}


def _locate_row(frame, rule):
    matches = []
    for result in rule.detect_and_ocr(frame):
        if ''.join(result.ocr_text.split()) != ''.join(rule.keyword.split()):
            continue
        box = result.box
        x, y = int(box[0, 0] + rule.roi[0]), int(box[0, 1] + rule.roi[1])
        w, h = int(box[1, 0] - box[0, 0]), int(box[2, 1] - box[0, 1])
        if w > 0 and h > 0:
            matches.append((x + w + 10, y - 10, 80, h + 20))
    return matches[0] if len(matches) == 1 else None


def _switch(frame, area):
    x, y, w, h = area
    x, y = max(0, x), max(0, y)
    patch = frame[y:min(frame.shape[0], y+h), x:min(frame.shape[1], x+w)]
    results = []
    for label, rule in (('on', Buff.I_OPEN_YELLOW), ('off', Buff.I_CLOSE_RED)):
        template = rule.image
        if patch.shape[0] < template.shape[0] or patch.shape[1] < template.shape[1]:
            continue
        scores = cv2.matchTemplate(patch, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, point = cv2.minMaxLoc(scores)
        results.append((score, label, (x+point[0]+template.shape[1]//2,
                                      y+point[1]+template.shape[0]//2)))
    results.sort(reverse=True)
    if not results or results[0][0] < .75 or (len(results) > 1 and results[0][0]-results[1][0] < .08):
        # The remaining-time digits change and sometimes degrade template
        # matching. A fully visible red bar can still confirm the off state.
        # Never infer an enabled state from this fallback.
        if y >= 120 and y+h <= 480 and patch.size:
            hsv = cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)
            red = (((hsv[:, :, 0] < 10) | (hsv[:, :, 0] > 170))
                   & (hsv[:, :, 1] > 120) & (hsv[:, :, 2] > 90)).mean()
            yellow = ((hsv[:, :, 0] >= 12) & (hsv[:, :, 0] <= 35)
                      & (hsv[:, :, 1] > 120) & (hsv[:, :, 2] > 120)).mean()
            if red > .23 and yellow < .08:
                return 'off', (x + 13, y + h // 2)
        return None
    return results[0][1:]


class MasterBuffs:
    def __init__(self, master):
        self.master = master

    def _panel(self, opened, timeout=15):
        deadline = time.monotonic() + timeout
        last_click = 0
        while time.monotonic() < deadline:
            self.master.screenshot()
            image = self.master.image
            panel = Buff.I_CLOUD.match(image)
            if panel == opened:
                return True
            if Buff.I_BUFF_1.match(image) and time.monotonic()-last_click > 3:
                self.master.click(379, 55, control_name='mentorship_buff_panel')
                last_click = time.monotonic()
                # The panel slides in over about two seconds; tapping again
                # before it settles toggles it straight back closed.
                time.sleep(1.5)
            time.sleep(.2)
        return False

    def set(self, name, enabled, timeout=25):
        if name not in _RULES:
            return False
        target = 'on' if enabled else 'off'
        for _ in range(2):
            if not self._panel(True):
                self._panel(False)
                continue
            settled = self._toggle(name, target, timeout)
            closed = self._panel(False)
            if settled and closed:
                return True
        return False

    def _toggle(self, name, target, timeout):
        deadline = time.monotonic() + timeout
        stable, last_click, swipes = 0, 0, 0
        while time.monotonic() < deadline:
            self.master.screenshot()
            image = self.master.image
            if not Buff.I_CLOUD.match(image):
                return False
            area = _locate_row(image, _RULES[name])
            state = _switch(image, area) if area else None
            if state and state[0] == target:
                stable += 1
                if stable >= 2:
                    return True
            else:
                stable = 0
                now = time.monotonic()
                if state and now-last_click > 1:
                    self.master.click(*state[1], control_name='mentorship_buff_'+name)
                    last_click = now
                elif not state and now-last_click > 1.5 and swipes < 4:
                    self.master.swipe([580, 320], [530, 240], control_name='mentorship_buff_scroll')
                    last_click, swipes = now, swipes + 1
            time.sleep(.2)
        return False
