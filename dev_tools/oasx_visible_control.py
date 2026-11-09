"""Operate only the visible OASX window, never a MuMu/game window.

Coordinates must be supplied from the immediately preceding inspected image.
No HTTP or hidden-process startup fallback is implemented.
"""

import argparse
import ctypes
import json
import tempfile
import time
from pathlib import Path

import win32con
import win32gui
import win32process
import pywintypes
from PIL import ImageGrab


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--click', nargs=2, type=int, metavar=('X', 'Y'))
    args = parser.parse_args()
    ctypes.windll.user32.SetProcessDPIAware()
    handle = win32gui.FindWindow(None, 'oasx')
    if not handle:
        raise SystemExit('Visible OASX is not open; no action taken')
    win32gui.ShowWindow(handle, win32con.SW_RESTORE)
    was_topmost = bool(win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST)
    win32gui.SetWindowPos(handle, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                         win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    foreground_thread = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[0]
    attached = False
    try:
        if current_thread != foreground_thread:
            attached = bool(ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, True))
        try:
            win32gui.SetForegroundWindow(handle)
        except pywintypes.error:
            # Windows may prohibit focus stealing. A click is still allowed
            # only if hit testing proves this exact OASX control is visible.
            pass
    finally:
        if attached:
            ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, False)
    time.sleep(0.3)
    if not win32gui.IsWindowVisible(handle):
        raise SystemExit('OASX is not visible; no action taken')
    left, top, right, bottom = win32gui.GetWindowRect(handle)
    if args.click:
        x, y = args.click
        if not (0 < x < right - left and 0 < y < bottom - top):
            raise SystemExit('Click outside OASX; no action taken')
        hit = win32gui.WindowFromPoint((left + x, top + y))
        if win32gui.GetAncestor(hit, win32con.GA_ROOT) != handle:
            raise SystemExit('OASX control is obscured; no action taken')
        ctypes.windll.user32.SetCursorPos(left + x, top + y)
        ctypes.windll.user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.6)
    output = Path(tempfile.gettempdir()) / 'oasx-visible-latest.png'
    ImageGrab.grab(bbox=(left, top, right, bottom)).save(output)
    if not was_topmost:
        win32gui.SetWindowPos(handle, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
    print(json.dumps({'window': handle, 'rect': [left, top, right, bottom],
                      'image': str(output), 'click': args.click}))


if __name__ == '__main__':
    main()
