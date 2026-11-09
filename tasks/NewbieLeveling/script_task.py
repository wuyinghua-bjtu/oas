"""Deterministic small-account SOP runner. No remote model or LLM calls.

This verified slice supports starter-courtyard identity and level, recorded
forest NPCs/dialogues/eye prompts, and action-free movie/dialogue waiting.
Unrecorded screens stop with evidence; they are not treated as supported by
a generic click/confirmation loop.
"""

import json
import os
import re
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PIL import Image

from module.exception import (
    GameSessionExpiredError, GameStuckError, GameNotRunningError,
    GameTooManyClickError, RequestHumanTakeover, ScriptEnd,
)
from module.logger import logger
from tasks.base_task import BaseTask
from tasks.NewbieLeveling.policy import (
    Observation, Progress, SessionState, checkpoint_from_dict,
    checkpoint_to_dict, evaluate, SUPPORTED_STORY_PAGES, MAX_SESSION_RETURNS,
)
from tasks.NewbieLeveling.vision import NewbieVision


class ScriptTask(BaseTask):
    """Only actions backed by local observations reach the device boundary."""

    @staticmethod
    def validate_profile(config):
        """Validate before constructing Device (which may otherwise recover it)."""
        name = config.config_name
        if name != 'oas_leveling' or not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ScriptEnd('NewbieLeveling is restricted to the isolated oas_leveling profile')
        device = config.script.device
        binding = (device.serial, device.handle, device.emulatorinfo_name)
        if binding != ('127.0.0.1:16416', 'MuMu安卓设备-1', 'MuMuPlayer-15.0-1'):
            raise ScriptEnd('NewbieLeveling device binding mismatch; no action allowed')
        if (device.screenshot_method != 'window_background' or
                device.control_method != 'window_message' or
                device.package_name != 'com.netease.onmyoji'):
            raise ScriptEnd('NewbieLeveling requires the verified screenshot/control/package binding')
        if config.script.optimization.queue_mode:
            raise ScriptEnd('NewbieLeveling does not allow shared queue/emulator recovery')
        enabled = [key for key, value in config.model.model_dump().items()
                   if isinstance(value, dict) and value.get('scheduler', {}).get('enable')
                   and key != 'newbie_leveling']
        if enabled:
            raise ScriptEnd('Disable other tasks in the leveling profile first: ' + ', '.join(enabled))

    def _prepare(self):
        self.validate_profile(self.config)
        self.settings = self.config.newbie_leveling.leveling_config
        name = self.config.config_name
        self.output = Path('log/newbie_leveling') / name
        self.output.mkdir(parents=True, exist_ok=True)
        self.checkpoint = self.output / 'checkpoint.json'
        self.progress = Progress()
        if self.checkpoint.exists():
            try:
                self.progress = checkpoint_from_dict(json.loads(self.checkpoint.read_text(encoding='utf-8')))
            except (ValueError, TypeError, OSError) as exc:
                raise ScriptEnd('Invalid leveling checkpoint; inspect it before resuming') from exc
        self.session = SessionState(started_at=time.monotonic())
        self.vision = NewbieVision()
        self._last_progress = self.progress
        self._last_target = None
        self._last_target_key = None
        self._target_count = 0
        self._pending = None
        self._transition_page = None
        self._transition_count = 0
        self._last_reason = None

    @staticmethod
    def _write_json(path, value):
        temporary = path.with_suffix(path.suffix + '.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)

    def _persist(self):
        if self.progress != self._last_progress:
            self._write_json(self.checkpoint, checkpoint_to_dict(self.progress))
            self._last_progress = self.progress

    def _evidence(self, tag, observation=None):
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        stem = self.output / (stamp + '-' + tag)
        image = getattr(self.device, 'image', None)
        if image is not None:
            Image.fromarray(image).save(stem.with_suffix('.png'))
        self._write_json(stem.with_suffix('.json'), {
            'tag': tag, 'time': datetime.now().isoformat(),
            'profile': self.config.config_name,
            'binding': self.config.script.device.serial,
            'progress': checkpoint_to_dict(self.progress),
            'session': asdict(self.session),
            'observation': asdict(observation) if observation is not None else None,
        })
        logger.info(f'LEVELING_EVIDENCE {stem}')

    def _finish(self, reason, completed=False, observation=None):
        self._persist()
        self._evidence('complete' if completed else 'paused', observation)
        self._write_json(self.output / 'status.json', {
            'status': 'completed' if completed else 'needs_attention',
            'reason': reason,
            'profile': self.config.config_name,
            'confirmed_level': self.progress.confirmed_level,
            'target_level': self.settings.target_level,
            'stamina_reserved': self.session.stamina_spent,
            'time': datetime.now().isoformat(),
        })
        if completed:
            self.config.newbie_leveling.scheduler.enable = False
            self.config.save()
            logger.info(f'LEVELING_COMPLETE target={self.settings.target_level}; task disabled')
        else:
            logger.warning(f'LEVELING_PAUSED {reason}; no automatic retry or purchase')
        # The scheduler handles this as a normal, bounded stop, not GameStuck.
        raise ScriptEnd(reason)

    def _stable_area(self, area, key=None):
        if key != self._last_target_key:
            self._last_target, self._target_count = None, 0
            self._last_target_key = key
        if area is None:
            self._last_target, self._target_count = None, 0
            return None
        if self._last_target and max(abs(a - b) for a, b in zip(area, self._last_target)) <= 8:
            self._target_count += 1
        else:
            self._target_count = 1
        self._last_target = area
        return area if self._target_count >= 2 else None

    def _candidate(self, visual):
        if visual.page in SUPPORTED_STORY_PAGES and not self.session.identity_verified:
            area = self._stable_area(visual.return_area, (visual.page, 'return'))
            if area is not None:
                return 'return_to_courtyard', area, 0
            return None, None, None
        if visual.page in SUPPORTED_STORY_PAGES and not self.session.level_verified:
            # Identity has been read in this run, but level needs another live
            # check. Only the verified return control may be proposed here.
            area = self._stable_area(visual.return_area, (visual.page, 'recheck'))
            if area is not None:
                return 'recheck_account', area, 0
            return None, None, None
        if visual.page == 'story_dialogue':
            area = self._stable_area(visual.story_skip_area, (visual.page, 'skip'))
            return ('story_skip', area, 0) if area is not None else (None, None, None)
        if visual.page == 'story_eye':
            area = self._stable_area(visual.tutorial_area, (visual.page, 'tutorial'))
            return ('tutorial_target', area, 0) if area is not None else (None, None, None)
        area = self._stable_area(visual.npc_story_area, (visual.page, 'npc'))
        if visual.page in ('courtyard', 'story_scene', 'story_reveal') and area is not None:
            return 'story_npc', area, 0
        return None, None, None

    def _execute(self, name, area, visual):
        # Keep an explicit executable whitelist in addition to the pure policy.
        # A future policy action alone cannot enable unverified UI behavior.
        valid_npc = (name == 'story_npc' and visual.page in ('courtyard', 'story_scene', 'story_reveal')
                     and area is not None and area == visual.npc_story_area)
        valid_return = (name == 'return_to_courtyard' and visual.page in SUPPORTED_STORY_PAGES
                        and area is not None and area == visual.return_area
                        and not self.session.identity_verified)
        # evaluate() has already consumed this return and cleared live trust.
        # Do not require identity_verified=True here, or merge this operation
        # into the separate unverified-session return_to_courtyard permission.
        valid_recheck = (name == 'recheck_account' and visual.page in SUPPORTED_STORY_PAGES
                         and area is not None and area == visual.return_area
                         and not self.session.identity_verified and not self.session.level_verified
                         and self.session.character_id == '' and self.session.return_attempted
                         and 1 <= self.session.return_count <= MAX_SESSION_RETURNS
                         and self.session.return_count == len(self.session.return_pages)
                         and self.session.return_pages[-1] == visual.page
                         and self.session.last_action_at is not None)
        valid_skip = (name == 'story_skip' and visual.page == 'story_dialogue'
                      and area is not None and area == visual.story_skip_area)
        valid_tutorial = (name == 'tutorial_target' and visual.page == 'story_eye'
                          and area is not None and area == visual.tutorial_area)
        if not (valid_npc or valid_return or valid_recheck or valid_skip or valid_tutorial):
            self._finish('unimplemented_action:' + str(name), observation=visual)
        x, y, width, height = area
        if width <= 0 or height <= 0 or not (0 <= x < x + width <= 1280 and 0 <= y < y + height <= 720):
            self._finish('invalid_action_area', observation=visual)
        self._evidence('before-' + name, visual)
        logger.info(f'LEVELING_ACTION {name} area={area} level={self.progress.confirmed_level}')
        try:
            self.device.click(x + width // 2, y + height // 2, control_name='NEWBIE_' + name.upper())
        except (GameSessionExpiredError, GameStuckError, GameNotRunningError,
                GameTooManyClickError, RequestHumanTakeover) as exc:
            self._finish('control_or_session_error:' + type(exc).__name__, observation=visual)
        self._pending = (name, visual.page, time.monotonic())
        self._transition_page, self._transition_count = None, 0
        self._last_target, self._target_count = None, 0

    def run(self):
        self._prepare()
        logger.info(f'LEVELING_START deterministic=true target={self.settings.target_level} '
                    f'observe_only={self.settings.observe_only}; '
                    'verified coverage=starter_courtyard,story_scene,story_dialogue,story_eye,story_reveal,'
                    'story_dialogue_wait,story_cinematic_wait')
        while True:
            try:
                # Session-loss handling in BaseTask is not used here: in a new
                # tutorial we must not launch the unrelated courtyard harvest.
                self.device.screenshot()
            except (GameSessionExpiredError, GameStuckError, GameNotRunningError,
                    GameTooManyClickError, RequestHumanTakeover) as exc:
                self._finish('capture_or_session_error:' + type(exc).__name__)
            if self.device.image.shape != (720, 1280, 3):
                self._finish('native_1280x720_required')
            visual = self.vision.observe(self.device.image)
            action, area, cost = self._candidate(visual)
            now = time.monotonic()
            if self._pending is not None:
                name, previous_page, issued_at = self._pending
                if visual.page != previous_page and visual.page != 'unknown':
                    self._transition_count = self._transition_count + 1 if self._transition_page == visual.page else 1
                    self._transition_page = visual.page
                else:
                    self._transition_page, self._transition_count = None, 0
                if self._transition_count >= 2:
                    self._evidence('after-' + name, visual)
                    logger.info(f'LEVELING_TRANSITION {previous_page} -> {visual.page}')
                    self._pending = None
                elif now - issued_at >= 12:
                    self._finish('action_transition_unverified:' + name, observation=visual)
                else:
                    action, area, cost = None, None, None
            observation = Observation(page=visual.page, level=visual.level,
                                      character_id=visual.identity, safe_action=action,
                                      action_cost=cost)
            device = self.config.script.device
            decision = evaluate(self.settings, self.progress, self.session, observation, now,
                                device.serial, device.handle, device.emulatorinfo_name)
            self.progress, self.session = decision.progress, decision.session
            self._persist()
            reason = (visual.page, decision.action, decision.reason, self.progress.confirmed_level)
            if reason != self._last_reason:
                logger.info(f'LEVELING_DECISION page={visual.page} level={visual.level} '
                            f'confirmed={self.progress.confirmed_level} action={decision.action} '
                            f'reason={decision.reason} vision={visual.reason}')
                self._last_reason = reason
            if decision.action in ('stop', 'complete'):
                self._finish(decision.reason, decision.action == 'complete', visual)
            if decision.action == 'execute':
                self._execute(decision.safe_action, area, visual)
            time.sleep(0.8)
