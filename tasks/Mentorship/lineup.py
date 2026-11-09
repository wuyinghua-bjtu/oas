"""Bounded lineup verification for both guardian-room clients."""
import time
from .vision import detect, lineup_state


def lock_guard_lineups(mentor, apprentice, verify_identity, timeout=15):
    """Return true only when the right apprentice and both locks are visible.

    verify_identity receives both current RGB images and must confirm that the
    configured apprentice is present. Unknown images never trigger a click.
    """
    deadline = time.monotonic() + timeout
    last_click = {'mentor': 0.0, 'apprentice': 0.0}
    while time.monotonic() < deadline:
        mentor.screenshot()
        apprentice.screenshot()
        m, a = mentor.image, apprentice.image
        if not (detect(m, 'guard_room') and detect(a, 'guard_room')
                and verify_identity(m, a)):
            time.sleep(0.2)
            continue
        states = {'mentor': lineup_state(m), 'apprentice': lineup_state(a)}
        if states['mentor'] == states['apprentice'] == 'lock':
            return True
        now = time.monotonic()
        for name, device in (('mentor', mentor), ('apprentice', apprentice)):
            if states[name] == 'unlock' and now - last_click[name] >= 1:
                device.click(70, 658)
                last_click[name] = now
        time.sleep(0.2)
    return False
