"""Fast, bounded handling of a guardian invitation on the apprentice device."""
import time
import cv2
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from .vision import guard_accept_position, detect


def accept_guard_invitation(device, timeout=15, interval=0.2, ready=None):
    """Accept only a recognized guardian banner; confirm the room afterwards.

    The caller should start this poll before sending the invitation. A click is
    never proof of joining: only the guardian room marker confirms the result.
    """
    deadline = time.monotonic() + timeout
    clicked = False
    last_click = 0.0
    saved = False
    if ready is not None:
        ready.set()
    while time.monotonic() < deadline:
        device.screenshot()
        image = device.image
        if not saved and deadline - time.monotonic() < timeout - 2:
            path = Path('log/mentorship/guard_invite_live.png')
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imencode('.png', cv2.cvtColor(image, cv2.COLOR_RGB2BGR))[1].tofile(str(path))
            saved = True
        if clicked and detect(image, 'guard_room'):
            return True
        point = guard_accept_position(image)
        now = time.monotonic()
        if point and now - last_click >= 1:
            device.click(*point)
            clicked = True
            last_click = now
        time.sleep(interval)
    return False


def invite_guard_with_listener(device, send_invitation, timeout=15):
    """Start listening before sending; only succeed after verified room entry."""
    ready = Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        listener = executor.submit(accept_guard_invitation, device, timeout, 0.2, ready)
        if not ready.wait(2):
            return False
        if not send_invitation():
            # The listener remains bounded even if sending failed.
            return False
        return listener.result()
