"""Pure, fail-closed policy; no OCR, device operations, files, network or LLM.

The caller supplies observations from its deterministic recognizer, executes
only the returned action, and persists ``checkpoint_to_dict(decision.progress)``.
Create a NEW SessionState for every run, even when restoring a checkpoint.
Only pass ``character_id`` when read from a trusted identity-bearing screen.
The script remains responsible for verifying action targets, obtaining fresh
frames, and capturing evidence on terminal decisions requesting it.
"""

from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import Any, Dict, Mapping, Optional, Tuple


EXPECTED_SERIAL = '127.0.0.1:16416'
EXPECTED_HANDLE = 'MuMu安卓设备-1'
EXPECTED_VM = 'MuMuPlayer-15.0-1'
SUPPORTED_STORY_PAGES = frozenset({'story_scene', 'story_dialogue', 'story_eye', 'story_reveal'})
MAX_SESSION_RETURNS = 2
CINEMATIC_WAIT_TIMEOUT_SECONDS = 90
SAFE_ACTIONS = frozenset({
    'story_npc', 'story_next', 'story_skip', 'tutorial_target',
    'battle_auto', 'battle_prepare', 'battle_settlement',
    'start_exploration', 'start_experience',
})
BATTLE_ENTRY_ACTIONS = frozenset({
    'battle_prepare', 'start_exploration', 'start_experience',
})
# An unexpectedly large jump can be an OCR confusion (e.g. 3 -> 30). Stop
# instead of accepting it, including when a player advanced the account offline.
MAX_LEVEL_JUMP = 3
MIN_LEVEL_SAMPLE_SECONDS = 0.5


@dataclass(frozen=True)
class Observation:
    page: str = 'unknown'
    level: Optional[int] = None
    stamina: Optional[int] = None
    character_id: Optional[str] = None
    safe_action: Optional[str] = None
    action_cost: Optional[int] = None


@dataclass(frozen=True)
class Progress:
    serial: str = ''
    character_id: str = ''
    confirmed_level: Optional[int] = None
    completed: bool = False


@dataclass(frozen=True)
class SessionState:
    started_at: float = 0.0
    identity_verified: bool = False
    character_id: str = ''
    candidate_level: Optional[int] = None
    candidate_count: int = 0
    last_level_sample_at: Optional[float] = None
    level_verified: bool = False
    unknown_since: Optional[float] = None
    cinematic_since: Optional[float] = None
    stamina_spent: int = 0
    last_action_at: Optional[float] = None
    # These navigation limits are session-only, never character progress.
    return_attempted: bool = False
    return_pages: Tuple[str, ...] = ()
    return_count: int = 0


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    progress: Progress
    session: SessionState
    safe_action: Optional[str] = None
    capture_evidence: bool = False


def checkpoint_to_dict(progress: Progress) -> Dict[str, Any]:
    return {'version': 1, **asdict(progress)}


def checkpoint_from_dict(data: Mapping[str, Any]) -> Progress:
    """Reject corrupt state; never coerce missing/invalid levels to zero."""
    if data.get('version') != 1:
        raise ValueError('Unsupported leveling checkpoint version')
    serial = data.get('serial')
    identity = data.get('character_id')
    level = data.get('confirmed_level')
    completed = data.get('completed')
    if not isinstance(serial, str) or not isinstance(identity, str):
        raise ValueError('Checkpoint identity must be text')
    if level is not None and not _valid_level(level):
        raise ValueError('Checkpoint level must be null or an integer from 1 to 60')
    if not isinstance(completed, bool):
        raise ValueError('Checkpoint completed flag must be boolean')
    if completed and (not serial or not identity or level is None):
        raise ValueError('Completed checkpoint requires identity and level')
    return Progress(serial, identity, level, completed)


def _valid_level(level: Any) -> bool:
    return type(level) is int and 1 <= level <= 60


def _valid_nonnegative(value: Any) -> bool:
    return type(value) is int and value >= 0


def _return_block_reason(session: SessionState, page: str) -> Optional[str]:
    # A legacy boolean-only state must not accidentally gain another attempt.
    if page in session.return_pages or (session.return_attempted and not session.return_pages):
        return 'story_return_already_attempted'
    if max(session.return_count, len(session.return_pages)) >= MAX_SESSION_RETURNS:
        return 'story_return_limit'
    return None


def evaluate(config, progress: Progress, session: SessionState,
             observation: Observation, now: float, actual_serial: str,
             actual_handle: str, actual_vm: str) -> Decision:
    """Return a new immutable state and at most one whitelisted action.

    ``now`` and ``started_at`` are monotonic seconds, never persisted. Cost is
    conservatively reserved when an action is issued, even if its click fails.
    A terminal stop is not an instruction to restart or reschedule the task.
    """
    def result(action, reason, evidence=False, safe_action=None):
        return Decision(action, reason, progress, session, safe_action, evidence)

    def cinematic_expired():
        return (session.cinematic_since is not None and
                now - session.cinematic_since >= CINEMATIC_WAIT_TIMEOUT_SECONDS)

    def uncertain(reason):
        nonlocal session
        cinematic = observation.page == 'story_cinematic_wait'
        if cinematic and observation.safe_action is not None:
            return result('stop', 'cinematic_actions_forbidden', True)
        if cinematic:
            since = session.cinematic_since if session.cinematic_since is not None else now
            # A verified animation is not an unknown-screen streak. Preserve
            # its separate overall deadline across page changes and re-entry.
            session = replace(session, cinematic_since=since, unknown_since=None)
        else:
            since = session.unknown_since if session.unknown_since is not None else now
            session = replace(session, unknown_since=since)
        if cinematic_expired():
            return result('stop', 'cinematic_wait_timeout', True)
        if not cinematic and now - since >= config.unknown_timeout_seconds:
            return result('stop', reason + '_timeout', True)
        return result('observe' if config.observe_only else 'wait', reason)

    if not isfinite(now) or not isfinite(session.started_at) or now < session.started_at:
        return result('stop', 'invalid_session_clock', True)
    expected = (EXPECTED_SERIAL, EXPECTED_HANDLE, EXPECTED_VM)
    configured = (config.expected_serial, config.expected_handle, config.expected_vm)
    if configured != expected or (actual_serial, actual_handle, actual_vm) != expected:
        return result('stop', 'instance_mismatch', True)
    if now - session.started_at >= config.session_minutes * 60:
        return result('stop', 'session_limit', True)

    if not session.identity_verified and observation.safe_action == 'return_to_courtyard':
        # This exception is navigation ONLY, not an account/level trust bypass.
        # It is intentionally absent from SAFE_ACTIONS so verified sessions
        # cannot use it to evade any of the normal level/target guards below.
        if observation.page not in SUPPORTED_STORY_PAGES:
            return result('stop', 'return_requires_verified_story_scene', True)
        if observation.level is not None or observation.character_id is not None:
            return result('stop', 'unexpected_account_data_on_story_return', True)
        if type(observation.action_cost) is not int or observation.action_cost != 0:
            return result('stop', 'story_return_must_be_explicitly_free', True)
        blocked = _return_block_reason(session, observation.page)
        if blocked:
            return result('stop', blocked, True)
        if cinematic_expired():
            return result('stop', 'cinematic_wait_timeout', True)
        since = session.unknown_since if session.unknown_since is not None else now
        session = replace(session, unknown_since=since)
        if now - since >= config.unknown_timeout_seconds:
            return result('stop', 'identity_unverified_timeout', True)
        if config.observe_only:
            return result('observe', 'observe_only', safe_action='return_to_courtyard')
        if (session.last_action_at is not None and
                now - session.last_action_at < config.action_interval_seconds):
            return result('wait', 'action_interval')
        session = replace(session, return_attempted=True, last_action_at=now, cinematic_since=None,
                          return_pages=session.return_pages + (observation.page,),
                          return_count=session.return_count + 1)
        return result('execute', 'return_for_live_identity', safe_action='return_to_courtyard')

    identity = (observation.character_id or '').strip()
    pinned_identity = config.character_id.strip()
    if identity:
        if pinned_identity and pinned_identity != identity:
            return result('stop', 'configured_character_mismatch', True)
        if session.identity_verified and session.character_id != identity:
            return result('stop', 'character_changed_during_session', True)
        if not session.identity_verified:
            # Old-account completion must not be reused for a new character.
            if progress.serial != actual_serial or progress.character_id != identity:
                progress = Progress(serial=actual_serial, character_id=identity)
            session = replace(session, identity_verified=True, character_id=identity)
    if not session.identity_verified:
        return uncertain('identity_unverified')
    if (progress.serial != actual_serial or progress.character_id != session.character_id):
        return result('stop', 'checkpoint_identity_mismatch', True)

    level = observation.level
    if _valid_level(level):
        previous = progress.confirmed_level
        if previous is not None and level < previous:
            return result('stop', 'level_regression', True)
        if previous is not None and level - previous > MAX_LEVEL_JUMP:
            return result('stop', 'implausible_level_jump', True)
        sample_due = (session.last_level_sample_at is None or
                      now - session.last_level_sample_at >= MIN_LEVEL_SAMPLE_SECONDS)
        if sample_due:
            count = session.candidate_count + 1 if session.candidate_level == level else 1
            session = replace(session, candidate_level=level, candidate_count=count,
                              last_level_sample_at=now)
            if count >= config.level_confirmations:
                progress = replace(progress, confirmed_level=level,
                                   completed=level >= config.target_level)
                session = replace(session, level_verified=True)
        # Even a single target-level reading blocks further actions while the
        # next independent frame confirms it.
        if level >= config.target_level:
            if (session.level_verified and progress.completed and
                    progress.confirmed_level == level and session.candidate_level == level and
                    session.candidate_count >= config.level_confirmations):
                return result('complete', 'target_reached', True)
            session = replace(session, level_verified=False)
            return uncertain('target_level_pending_confirmation')
    else:
        session = replace(session, candidate_level=None, candidate_count=0,
                          last_level_sample_at=None)
        if level is not None:
            return uncertain('invalid_level_reading')

    # A live-confirmed target remains terminal even when the next HUD hides it.
    # Restored checkpoints cannot satisfy this without live session verification.
    if (session.level_verified and progress.confirmed_level is not None and
            progress.confirmed_level >= config.target_level):
        progress = replace(progress, completed=True)
        return result('complete', 'target_reached', True)
    # A recognized cinematic grants passive waiting only, never a new action.
    # Live target completion above retains priority over any screen action.
    if observation.page == 'story_cinematic_wait' and observation.safe_action is not None:
        return result('stop', 'cinematic_actions_forbidden', True)
    # A new visible button cannot revive an already-expired passive episode.
    # Only an actual execute decision before this deadline resets its clock.
    if cinematic_expired():
        return result('stop', 'cinematic_wait_timeout', True)
    if observation.safe_action == 'recheck_account':
        # Rechecking is a different operation from unverified-session recovery.
        # Live identity and any visible level/target guards above still apply.
        # A hidden/invalidated level must not prevent this navigation-only path
        # from reaching the courtyard where fresh confirmation is possible.
        if observation.page not in SUPPORTED_STORY_PAGES:
            return result('stop', 'recheck_requires_verified_story_page', True)
        if observation.level is not None or observation.character_id is not None:
            return result('stop', 'unexpected_account_data_on_recheck', True)
        if type(observation.action_cost) is not int or observation.action_cost != 0:
            return result('stop', 'account_recheck_must_be_explicitly_free', True)
        blocked = _return_block_reason(session, observation.page)
        if blocked:
            return result('stop', blocked, True)
        if not session.level_verified:
            since = session.unknown_since if session.unknown_since is not None else now
            session = replace(session, unknown_since=since)
            if now - since >= config.unknown_timeout_seconds:
                return result('stop', 'level_unverified_timeout', True)
        if config.observe_only:
            return result('observe', 'observe_only', safe_action='recheck_account')
        if (session.last_action_at is not None and
                now - session.last_action_at < config.action_interval_seconds):
            return result('wait', 'action_interval')
        # Count this physical return against the SAME two-return budget. A
        # newly read courtyard must not reset it and create a back/forth loop.
        session = replace(session, identity_verified=False, character_id='',
                          level_verified=False, candidate_level=None, candidate_count=0,
                          last_level_sample_at=None, unknown_since=now, last_action_at=now,
                          cinematic_since=None,
                          return_attempted=True, return_pages=session.return_pages + (observation.page,),
                          return_count=session.return_count + 1)
        return result('execute', 'recheck_live_account', safe_action='recheck_account')
    # Checkpoints alone are never enough to resume an old completed account.
    if progress.completed and not session.level_verified:
        return uncertain('completed_checkpoint_needs_live_level')
    # Finishing an already-started battle does not begin another one. Its HUD
    # normally hides account level, so these two controls may use the earlier
    # confirmed level while every next battle entry remains blocked.
    finishing_battle = (observation.safe_action in {'battle_auto', 'battle_settlement'} and
                        progress.confirmed_level is not None and not progress.completed)
    if not session.level_verified and not finishing_battle:
        return uncertain('level_unverified')
    if not observation.page or observation.page == 'unknown':
        return uncertain('unknown_page')
    if observation.safe_action is None:
        return uncertain('no_supported_action')
    if observation.safe_action not in SAFE_ACTIONS:
        return result('stop', 'forbidden_action', True)
    cost = observation.action_cost
    if not _valid_nonnegative(cost):
        return uncertain('action_cost_unverified')
    if observation.safe_action not in BATTLE_ENTRY_ACTIONS and cost != 0:
        return result('stop', 'non_battle_action_must_be_free', True)
    if observation.safe_action in BATTLE_ENTRY_ACTIONS and not _valid_nonnegative(observation.stamina):
        return uncertain('stamina_unverified')
    if cost > 0:
        if not _valid_nonnegative(observation.stamina):
            return uncertain('stamina_unverified')
        if observation.stamina < cost:
            return result('stop', 'insufficient_stamina', True)
    if session.stamina_spent + cost > config.stamina_budget:
        return result('stop', 'stamina_budget_exhausted', True)

    session = replace(session, unknown_since=None)
    if config.observe_only:
        return result('observe', 'observe_only', safe_action=observation.safe_action)
    if session.last_action_at is not None and now - session.last_action_at < config.action_interval_seconds:
        return result('wait', 'action_interval')
    session = replace(session, last_action_at=now, stamina_spent=session.stamina_spent + cost,
                      cinematic_since=None)
    if observation.safe_action in BATTLE_ENTRY_ACTIONS or observation.safe_action == 'battle_settlement':
        session = replace(session, level_verified=False, candidate_level=None,
                          candidate_count=0, last_level_sample_at=None)
    return result('execute', 'safe_action_ready', safe_action=observation.safe_action)
