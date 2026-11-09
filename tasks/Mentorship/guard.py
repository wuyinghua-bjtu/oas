"""Pure state decisions for recorded guardian-training screens."""
from enum import Enum
from .vision import detect, lineup_state


class GuardAction(Enum):
    OPEN_INVITE = 'open_invite'
    SELECT_APPRENTICE = 'select_apprentice'
    SEND_INVITE = 'send_invite'
    ACCEPT_INVITE = 'accept_invite'
    LOCK_MENTOR = 'lock_mentor'
    LOCK_APPRENTICE = 'lock_apprentice'
    START = 'start'
    WAIT = 'wait'


def decide_guard_invite(mentor_image, apprentice_image, candidate_text, expected_name,
                        *, candidate_selected=False, invitation_sent=False):
    """Never click an unmatched name or a different kind of invitation."""
    if detect(apprentice_image, 'guard_invitation'):
        return GuardAction.ACCEPT_INVITE
    if detect(mentor_image, 'guard_invite_title'):
        if ''.join(expected_name.split()) != ''.join(candidate_text.split()):
            return GuardAction.WAIT
        return GuardAction.SEND_INVITE if candidate_selected else GuardAction.SELECT_APPRENTICE
    if detect(mentor_image, 'guard_invite_entry'):
        return GuardAction.WAIT if invitation_sent else GuardAction.OPEN_INVITE
    return GuardAction.WAIT


def decide_guard_ready(mentor_image, apprentice_image, both_confirmed):
    if not both_confirmed or not detect(mentor_image, 'guard_room') or not detect(apprentice_image, 'guard_room'):
        return GuardAction.WAIT
    mentor_lock, apprentice_lock = lineup_state(mentor_image), lineup_state(apprentice_image)
    if mentor_lock == 'unlock':
        return GuardAction.LOCK_MENTOR
    if apprentice_lock == 'unlock':
        return GuardAction.LOCK_APPRENTICE
    if mentor_lock == apprentice_lock == 'lock':
        return GuardAction.START
    return GuardAction.WAIT
