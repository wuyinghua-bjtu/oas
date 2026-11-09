"""Read-only window-background evidence capture for the second MuMu only."""
import argparse
import time
from pathlib import Path

import win32con
import win32gui
import win32ui
from PIL import Image


def capture():
    root = win32gui.FindWindow(None, 'MuMu安卓设备-1')
    handle = win32gui.FindWindowEx(root, 0, None, 'MuMuNxDevice') if root else 0
    if not handle:
        raise RuntimeError('Second MuMu render window is not available')
    x1, y1, x2, y2 = win32gui.GetWindowRect(handle)
    width, height = x2 - x1, y2 - y1
    dc = win32gui.GetWindowDC(handle)
    source = win32ui.CreateDCFromHandle(dc)
    memory = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        memory.SelectObject(bitmap)
        memory.BitBlt((0, 0), (width, height), source, (0, 0), win32con.SRCCOPY)
        return Image.frombuffer('RGB', (width, height), bitmap.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(handle, dc)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--frames', type=int, default=1, choices=range(1, 21))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    for number in range(args.frames):
        image = capture()
        path = args.directory / f'{time.time_ns()}-{number:02d}.png'
        image.save(path)
        print(path, image.size)
        if number + 1 < args.frames:
            time.sleep(0.4)
