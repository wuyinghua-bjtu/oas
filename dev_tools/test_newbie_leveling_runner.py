"""Offline runner/scheduler regression tests; never construct a real Device.

Run: toolkit/python.exe -m unittest dev_tools.test_newbie_leveling_runner
Every write is directed to a temporary directory. Vision, screenshots, clicks,
and time are mocked; these tests neither connect to MuMu nor run OCR.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import numpy as np

from module.device.device import Device
from module.exception import (
    GameNotRunningError, GameSessionExpiredError, GameStuckError, GameTooManyClickError,
    RequestHumanTakeover, ScriptEnd,
)
from script import Script
from tasks.NewbieLeveling.config import LevelingConfig, NewbieLeveling
from tasks.NewbieLeveling.device import LevelingDevice
from tasks.NewbieLeveling.policy import (
    EXPECTED_HANDLE, EXPECTED_SERIAL, EXPECTED_VM, Progress, SessionState, checkpoint_to_dict,
)
from tasks.NewbieLeveling.script_task import ScriptTask
from tasks.NewbieLeveling.vision import VisionObservation


RUNNER = 'tasks.NewbieLeveling.script_task'
AREA = (731, 265, 20, 18)
SCENE_AREA = (180, 250, 20, 18)
RETURN_AREA = (30, 24, 30, 30)
SKIP_AREA = (1140, 24, 70, 32)
EYE_AREA = (950, 84, 32, 32)
QUESTION_AREA = (530, 302, 18, 20)


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class NewbieRunnerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='oas-newbie-runner-test-')
        self.addCleanup(directory.cleanup)
        self.output_root = Path(directory.name)
        self.output = self.output_root / 'oas_leveling'
        self.clock = FakeClock()
        self.visuals = []
        self.default_visual = VisionObservation()
        self.screenshot_count = 0
        self.task = object.__new__(ScriptTask)
        self.task.device = Mock()
        self.task.device.image = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.task.device.screenshot.side_effect = self.screenshot
        settings = LevelingConfig(observe_only=False, unknown_timeout_seconds=5)
        task_config = NewbieLeveling(leveling_config=settings)
        task_config.scheduler.enable = True
        binding = SimpleNamespace(serial=EXPECTED_SERIAL, handle=EXPECTED_HANDLE,
                                  emulatorinfo_name=EXPECTED_VM,
                                  screenshot_method='window_background',
                                  control_method='window_message',
                                  package_name='com.netease.onmyoji')
        self.task.config = SimpleNamespace(
            config_name='oas_leveling', newbie_leveling=task_config,
            script=SimpleNamespace(device=binding, optimization=SimpleNamespace(queue_mode=False)),
            model=Mock(model_dump=Mock(return_value={
                'newbie_leveling': {'scheduler': {'enable': True}},
            })), save=Mock(),
        )
        self.vision = Mock()
        self.vision.observe.side_effect = self.observe

    def screenshot(self):
        self.screenshot_count += 1
        if self.screenshot_count > 80:
            raise AssertionError('Runner failed to stop within its mocked time budget')
        return self.task.device.image

    def observe(self, image):
        return self.visuals.pop(0) if self.visuals else self.default_visual

    @staticmethod
    def courtyard(level=3, area=None, identity='测试角色土'):
        return VisionObservation(page='courtyard', level=level, identity=identity,
                                 npc_story_area=area, reason='offline_fixture')

    def run_task(self):
        with patch(RUNNER + '.Path', return_value=self.output_root), \
                patch(RUNNER + '.NewbieVision', return_value=self.vision), \
                patch(RUNNER + '.time.monotonic', side_effect=self.clock.monotonic), \
                patch(RUNNER + '.time.sleep', side_effect=self.clock.sleep), \
                patch(RUNNER + '.logger'):
            self.task.run()

    def status(self):
        return json.loads((self.output / 'status.json').read_text(encoding='utf-8'))

    def checkpoint(self):
        return json.loads((self.output / 'checkpoint.json').read_text(encoding='utf-8'))

    def test_instance_mismatch_stops_before_screenshot_or_click(self):
        self.task.config.script.device.serial = '127.0.0.1:16384'
        with self.assertRaisesRegex(ScriptEnd, 'binding mismatch'):
            self.run_task()
        self.task.device.screenshot.assert_not_called()
        self.task.device.click.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_wrong_profile_stops_before_screenshot_or_click(self):
        self.task.config.config_name = 'oas1'
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.task.device.screenshot.assert_not_called()
        self.task.device.click.assert_not_called()

    def test_shared_queue_is_rejected_before_screenshot_or_click(self):
        self.task.config.script.optimization.queue_mode = True
        with self.assertRaisesRegex(ScriptEnd, 'shared queue'):
            self.run_task()
        self.task.device.screenshot.assert_not_called()
        self.task.device.click.assert_not_called()

    def test_level_30_is_confirmed_twice_then_disables_task_without_click(self):
        self.default_visual = self.courtyard(level=30, area=AREA)
        with self.assertRaisesRegex(ScriptEnd, 'target_reached'):
            self.run_task()
        self.assertEqual(self.vision.observe.call_count, 2)
        self.task.device.click.assert_not_called()
        self.assertFalse(self.task.config.newbie_leveling.scheduler.enable)
        self.task.config.save.assert_called_once()
        self.assertEqual(self.status()['status'], 'completed')
        self.assertTrue(self.checkpoint()['completed'])
        self.assertEqual(self.checkpoint()['confirmed_level'], 30)

    def test_unknown_page_has_bounded_exit_and_evidence_without_click(self):
        self.visuals = [self.courtyard(), self.courtyard()]
        with self.assertRaisesRegex(ScriptEnd, 'unknown_page_timeout'):
            self.run_task()
        self.task.device.click.assert_not_called()
        self.assertLessEqual(self.screenshot_count, 12)
        self.assertEqual(self.status()['status'], 'needs_attention')
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)
        self.assertTrue(list(self.output.glob('*-paused.png')))
        self.assertTrue(list(self.output.glob('*-paused.json')))

    def test_npc_to_two_dialogue_wait_frames_confirms_transition_without_dialogue_click(self):
        courtyard = self.courtyard(area=AREA)
        wait = VisionObservation(page='story_dialogue_wait', reason='offline_auto_dialogue')
        self.visuals = [courtyard, courtyard, wait, wait]
        self.default_visual = wait
        pending_before_frame = []
        original_observe = self.observe

        def observe(image):
            pending_before_frame.append(self.task._pending)
            return original_observe(image)

        self.vision.observe.side_effect = observe
        with self.assertRaisesRegex(ScriptEnd, 'no_supported_action_timeout'):
            self.run_task()
        self.assertIsNotNone(pending_before_frame[2])  # Before first wait frame.
        self.assertIsNotNone(pending_before_frame[3])  # One frame is insufficient.
        self.assertIsNone(pending_before_frame[4])     # Two wait frames confirmed.
        self.assertIsNone(self.task._pending)
        self.task.device.click.assert_called_once_with(
            AREA[0] + AREA[2] // 2, AREA[1] + AREA[3] // 2,
            control_name='NEWBIE_STORY_NPC')
        evidence = list(self.output.glob('*-after-story_npc.json'))
        self.assertEqual(len(evidence), 1)
        record = json.loads(evidence[0].read_text(encoding='utf-8'))
        self.assertEqual(record['observation']['page'], 'story_dialogue_wait')

    def test_continuous_dialogue_wait_is_bounded_by_unknown_timeout(self):
        self.visuals = [self.courtyard(), self.courtyard()]
        self.default_visual = VisionObservation(page='story_dialogue_wait', reason='offline_auto_dialogue')
        with self.assertRaisesRegex(ScriptEnd, 'no_supported_action_timeout'):
            self.run_task()
        timeout = self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds
        self.assertGreaterEqual(self.clock.now - self.task.session.started_at, timeout)
        self.assertLess(self.clock.now - self.task.session.started_at, timeout + 0.81)
        self.task.device.click.assert_not_called()
        self.assertEqual(self.status()['status'], 'needs_attention')
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)

    def test_unverified_dialogue_wait_never_returns_or_clicks(self):
        self.default_visual = VisionObservation(page='story_dialogue_wait', reason='offline_auto_dialogue')
        with self.assertRaisesRegex(ScriptEnd, 'identity_unverified_timeout'):
            self.run_task()
        self.task.device.click.assert_not_called()
        self.assertFalse(self.task.session.identity_verified)
        self.assertFalse(self.task.session.return_attempted)
        self.assertEqual(self.task.session.return_count, 0)
        self.assertIsNone(self.task.progress.confirmed_level)
        self.assertLessEqual(self.task.device.screenshot.call_count, 9)

    def test_persistent_story_bubble_is_clicked_only_once(self):
        self.default_visual = self.courtyard(area=AREA)
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.task.device.click.assert_called_once_with(
            AREA[0] + AREA[2] // 2, AREA[1] + AREA[3] // 2,
            control_name='NEWBIE_STORY_NPC')
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)
        self.assertLessEqual(self.screenshot_count, 22)

    def test_single_unknown_frame_is_not_a_confirmed_transition_or_second_click(self):
        courtyard = self.courtyard(area=AREA)
        self.visuals = [courtyard, courtyard, VisionObservation(), courtyard]
        self.default_visual = courtyard
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.assertEqual(self.task.device.click.call_count, 1)

    def test_full_story_return_identity_and_two_npc_sequence_stops_at_unknown(self):
        settings = self.task.config.newbie_leveling.leveling_config
        settings.unknown_timeout_seconds = 30
        # Keep the production action interval guard active; at one second the
        # two 0.8-second frame confirmations also satisfy it for this fixture.
        settings.action_interval_seconds = 1.0
        scene = VisionObservation(page='story_scene', npc_story_area=SCENE_AREA,
                                  return_area=RETURN_AREA, reason='offline_scene')
        courtyard = self.courtyard(area=AREA)
        self.visuals = [scene, scene, courtyard, courtyard, scene, scene]
        click_times = []
        self.task.device.click.side_effect = lambda *args, **kwargs: click_times.append(self.clock.now)
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:story_npc'):
            self.run_task()
        expected = [
            call(RETURN_AREA[0] + RETURN_AREA[2] // 2, RETURN_AREA[1] + RETURN_AREA[3] // 2,
                 control_name='NEWBIE_RETURN_TO_COURTYARD'),
            call(AREA[0] + AREA[2] // 2, AREA[1] + AREA[3] // 2,
                 control_name='NEWBIE_STORY_NPC'),
            call(SCENE_AREA[0] + SCENE_AREA[2] // 2, SCENE_AREA[1] + SCENE_AREA[3] // 2,
                 control_name='NEWBIE_STORY_NPC'),
        ]
        self.assertEqual(self.task.device.click.call_args_list, expected)
        self.assertTrue(self.task.session.return_attempted)
        self.assertTrue(self.task.session.identity_verified)
        self.assertEqual(self.task.session.stamina_spent, 0)
        self.assertEqual(self.status()['stamina_reserved'], 0)
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)
        self.assertFalse(self.checkpoint()['completed'])
        self.assertGreaterEqual(self.clock.now - click_times[-1], 12)
        self.assertLess(self.clock.now - click_times[-1], 13)
        self.assertLessEqual(self.vision.observe.call_count, 23)

    def test_one_known_scene_frame_does_not_clear_pending_or_repeat_courtyard_click(self):
        courtyard = self.courtyard(area=AREA)
        scene = VisionObservation(page='story_scene', npc_story_area=SCENE_AREA,
                                  return_area=RETURN_AREA, reason='offline_scene')
        self.visuals = [courtyard, courtyard, scene, courtyard]
        self.default_visual = courtyard
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.task.device.click.assert_called_once_with(
            AREA[0] + AREA[2] // 2, AREA[1] + AREA[3] // 2,
            control_name='NEWBIE_STORY_NPC')
        self.assertFalse(self.task.session.return_attempted)

    def test_full_story_sequence_also_respects_default_two_second_action_interval(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        self.assertEqual(self.task.config.newbie_leveling.leveling_config.action_interval_seconds, 2.0)
        scene = VisionObservation(page='story_scene', npc_story_area=SCENE_AREA,
                                  return_area=RETURN_AREA, reason='offline_scene')
        courtyard = self.courtyard(area=AREA)
        # Confirmation succeeds at two frames, then the default action-rate
        # guard deliberately waits for a third frame before the next click.
        self.visuals = [scene, scene, courtyard, courtyard, courtyard, scene, scene, scene]
        click_times = []
        self.task.device.click.side_effect = lambda *args, **kwargs: click_times.append(self.clock.now)
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:story_npc'):
            self.run_task()
        self.assertEqual([item.kwargs['control_name'] for item in self.task.device.click.call_args_list],
                         ['NEWBIE_RETURN_TO_COURTYARD', 'NEWBIE_STORY_NPC', 'NEWBIE_STORY_NPC'])
        self.assertTrue(all(second - first >= 2.0 for first, second in zip(click_times, click_times[1:])))
        self.assertEqual(self.task.session.stamina_spent, 0)
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)

    def test_known_identity_never_uses_return_button_when_scene_npc_is_missing(self):
        self.visuals = [self.courtyard(), self.courtyard()]
        self.default_visual = VisionObservation(page='story_scene', return_area=RETURN_AREA,
                                               reason='offline_scene_without_npc')
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.assertTrue(self.task.session.identity_verified)
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)
        self.task.device.click.assert_not_called()
        self.assertFalse(self.task.session.return_attempted)

    def test_fresh_dialogue_uses_only_return_not_visible_skip(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        self.default_visual = VisionObservation(page='story_dialogue', return_area=RETURN_AREA,
                                               story_skip_area=SKIP_AREA, reason='offline_dialogue')
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:return_to_courtyard'):
            self.run_task()
        self.task.device.click.assert_called_once_with(
            RETURN_AREA[0] + RETURN_AREA[2] // 2, RETURN_AREA[1] + RETURN_AREA[3] // 2,
            control_name='NEWBIE_RETURN_TO_COURTYARD')
        self.assertFalse(self.task.session.identity_verified)
        self.assertIsNone(self.task.progress.confirmed_level)

    def test_fresh_eye_uses_only_return_not_visible_tutorial_target(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        self.default_visual = VisionObservation(page='story_eye', return_area=RETURN_AREA,
                                               tutorial_area=EYE_AREA, reason='offline_eye')
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:return_to_courtyard'):
            self.run_task()
        self.task.device.click.assert_called_once_with(
            RETURN_AREA[0] + RETURN_AREA[2] // 2, RETURN_AREA[1] + RETURN_AREA[3] // 2,
            control_name='NEWBIE_RETURN_TO_COURTYARD')
        self.assertFalse(self.task.session.identity_verified)
        self.assertIsNone(self.task.progress.confirmed_level)

    def test_fresh_dialogue_without_return_cannot_use_its_skip_button(self):
        self.default_visual = VisionObservation(page='story_dialogue', story_skip_area=SKIP_AREA,
                                               reason='offline_dialogue_without_return')
        with self.assertRaisesRegex(ScriptEnd, 'identity_unverified_timeout'):
            self.run_task()
        self.task.device.click.assert_not_called()

    def test_dialogue_return_courtyard_confirmation_skip_and_eye_are_ordered(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        dialogue = VisionObservation(page='story_dialogue', return_area=RETURN_AREA,
                                     story_skip_area=SKIP_AREA, reason='offline_dialogue')
        eye = VisionObservation(page='story_eye', return_area=RETURN_AREA,
                                tutorial_area=EYE_AREA, reason='offline_eye')
        # Default two-second action interval still applies between skip/eye;
        # eye is confirmed on its second frame and clicked on its third.
        self.visuals = [dialogue, dialogue, self.courtyard(), self.courtyard(),
                        dialogue, dialogue, eye, eye, eye]
        click_frames = []
        self.task.device.click.side_effect = lambda *args, **kwargs: click_frames.append(self.vision.observe.call_count)
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:tutorial_target'):
            self.run_task()
        self.assertEqual(self.task.device.click.call_args_list, [
            call(RETURN_AREA[0] + RETURN_AREA[2] // 2, RETURN_AREA[1] + RETURN_AREA[3] // 2,
                 control_name='NEWBIE_RETURN_TO_COURTYARD'),
            call(SKIP_AREA[0] + SKIP_AREA[2] // 2, SKIP_AREA[1] + SKIP_AREA[3] // 2,
                 control_name='NEWBIE_STORY_SKIP'),
            call(EYE_AREA[0] + EYE_AREA[2] // 2, EYE_AREA[1] + EYE_AREA[3] // 2,
                 control_name='NEWBIE_TUTORIAL_TARGET'),
        ])
        self.assertEqual(click_frames, [2, 6, 9])
        self.assertTrue(self.task.session.identity_verified)
        self.assertEqual(self.task.session.return_count, 1)
        self.assertEqual(self.task.session.stamina_spent, 0)
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)

    def test_one_courtyard_level_frame_after_return_does_not_unlock_eye_target(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        eye = VisionObservation(page='story_eye', return_area=RETURN_AREA,
                                tutorial_area=EYE_AREA, reason='offline_eye')
        self.visuals = [eye, eye, self.courtyard(), eye, eye]
        self.default_visual = eye
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.assertEqual([item.kwargs['control_name'] for item in self.task.device.click.call_args_list],
                         ['NEWBIE_RETURN_TO_COURTYARD'])
        self.assertFalse(self.task.session.level_verified)
        self.assertIsNone(self.task.progress.confirmed_level)

    def test_persistent_dialogue_skip_is_clicked_once_then_stops_after_twelve_seconds(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        self.visuals = [self.courtyard(), self.courtyard()]
        self.default_visual = VisionObservation(page='story_dialogue', return_area=RETURN_AREA,
                                               story_skip_area=SKIP_AREA, reason='offline_dialogue')
        click_times = []
        self.task.device.click.side_effect = lambda *args, **kwargs: click_times.append(self.clock.now)
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:story_skip'):
            self.run_task()
        self.task.device.click.assert_called_once_with(
            SKIP_AREA[0] + SKIP_AREA[2] // 2, SKIP_AREA[1] + SKIP_AREA[3] // 2,
            control_name='NEWBIE_STORY_SKIP')
        self.assertGreaterEqual(self.clock.now - click_times[0], 12)
        self.assertLess(self.clock.now - click_times[0], 13)
        self.assertFalse(self.task.session.return_attempted)

    def test_one_eye_frame_cannot_clear_dialogue_pending_or_repeat_skip(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        dialogue = VisionObservation(page='story_dialogue', story_skip_area=SKIP_AREA,
                                     reason='offline_dialogue')
        eye = VisionObservation(page='story_eye', tutorial_area=EYE_AREA, reason='offline_eye')
        self.visuals = [self.courtyard(), self.courtyard(), dialogue, dialogue, eye, dialogue]
        self.default_visual = dialogue
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:story_skip'):
            self.run_task()
        self.task.device.click.assert_called_once_with(
            SKIP_AREA[0] + SKIP_AREA[2] // 2, SKIP_AREA[1] + SKIP_AREA[3] // 2,
            control_name='NEWBIE_STORY_SKIP')

    def test_verified_story_pages_without_action_buttons_cannot_click_return(self):
        self.visuals = [self.courtyard(), self.courtyard(),
                        VisionObservation(page='story_dialogue', return_area=RETURN_AREA)]
        self.default_visual = VisionObservation(page='story_eye', return_area=RETURN_AREA)
        with self.assertRaisesRegex(ScriptEnd, 'no_supported_action_timeout'):
            self.run_task()
        self.task.device.click.assert_not_called()

    def test_equal_button_rectangles_across_pages_do_not_share_stability(self):
        dialogue = VisionObservation(page='story_dialogue', story_skip_area=EYE_AREA)
        eye = VisionObservation(page='story_eye', tutorial_area=EYE_AREA)
        self.visuals = [self.courtyard(), self.courtyard(), dialogue, eye]
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.task.device.click.assert_not_called()

    def test_fresh_reveal_returns_then_requires_courtyard_before_question_npc(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        reveal = VisionObservation(page='story_reveal', npc_story_area=QUESTION_AREA,
                                   return_area=RETURN_AREA, reason='offline_reveal')
        self.visuals = [reveal, reveal, self.courtyard(), self.courtyard(), reveal, reveal]
        click_frames = []
        self.task.device.click.side_effect = lambda *args, **kwargs: click_frames.append(self.vision.observe.call_count)
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:story_npc'):
            self.run_task()
        self.assertEqual(self.task.device.click.call_args_list, [
            call(RETURN_AREA[0] + RETURN_AREA[2] // 2, RETURN_AREA[1] + RETURN_AREA[3] // 2,
                 control_name='NEWBIE_RETURN_TO_COURTYARD'),
            call(QUESTION_AREA[0] + QUESTION_AREA[2] // 2, QUESTION_AREA[1] + QUESTION_AREA[3] // 2,
                 control_name='NEWBIE_STORY_NPC'),
        ])
        self.assertEqual(click_frames, [2, 6])
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)
        self.assertEqual(self.task.session.stamina_spent, 0)

    def test_fresh_reveal_without_return_cannot_trust_a_saved_level(self):
        self.output.mkdir()
        old_progress = Progress(EXPECTED_SERIAL, '测试角色土', 3)
        ScriptTask._write_json(self.output / 'checkpoint.json', checkpoint_to_dict(old_progress))
        self.default_visual = VisionObservation(page='story_reveal', npc_story_area=QUESTION_AREA,
                                               reason='offline_reveal_without_return')
        with self.assertRaisesRegex(ScriptEnd, 'identity_unverified_timeout'):
            self.run_task()
        self.task.device.click.assert_not_called()
        self.assertEqual(self.task.progress, old_progress)
        self.assertFalse(self.task.session.identity_verified)
        self.assertFalse(self.task.session.level_verified)

    def test_verified_persistent_reveal_question_is_clicked_once(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        self.visuals = [self.courtyard(), self.courtyard()]
        self.default_visual = VisionObservation(page='story_reveal', npc_story_area=QUESTION_AREA,
                                               return_area=RETURN_AREA, reason='offline_reveal')
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:story_npc'):
            self.run_task()
        self.task.device.click.assert_called_once_with(
            QUESTION_AREA[0] + QUESTION_AREA[2] // 2, QUESTION_AREA[1] + QUESTION_AREA[3] // 2,
            control_name='NEWBIE_STORY_NPC')
        self.assertFalse(self.task.session.return_attempted)

    def test_reveal_to_dialogue_requires_two_known_frames_before_next_action(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        reveal = VisionObservation(page='story_reveal', npc_story_area=QUESTION_AREA)
        dialogue = VisionObservation(page='story_dialogue', story_skip_area=SKIP_AREA)
        self.visuals = [self.courtyard(), self.courtyard(), reveal, reveal, dialogue, dialogue, dialogue]
        click_frames = []
        self.task.device.click.side_effect = lambda *args, **kwargs: click_frames.append(self.vision.observe.call_count)
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:story_skip'):
            self.run_task()
        self.assertEqual([item.kwargs['control_name'] for item in self.task.device.click.call_args_list],
                         ['NEWBIE_STORY_NPC', 'NEWBIE_STORY_SKIP'])
        self.assertEqual(click_frames, [4, 7])

    def test_one_dialogue_flash_does_not_repeat_reveal_question(self):
        self.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        reveal = VisionObservation(page='story_reveal', npc_story_area=QUESTION_AREA)
        dialogue = VisionObservation(page='story_dialogue', story_skip_area=SKIP_AREA)
        self.visuals = [self.courtyard(), self.courtyard(), reveal, reveal, dialogue, reveal]
        self.default_visual = reveal
        with self.assertRaisesRegex(ScriptEnd, 'action_transition_unverified:story_npc'):
            self.run_task()
        self.assertEqual(self.task.device.click.call_count, 1)

    def test_reveal_cannot_reuse_an_equal_scene_npc_stability_sample(self):
        scene = VisionObservation(page='story_scene', npc_story_area=QUESTION_AREA)
        reveal = VisionObservation(page='story_reveal', npc_story_area=QUESTION_AREA)
        self.visuals = [self.courtyard(), self.courtyard(), scene, reveal]
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.task.device.click.assert_not_called()

    def test_verified_reveal_without_question_npc_has_no_action(self):
        self.visuals = [self.courtyard(), self.courtyard()]
        self.default_visual = VisionObservation(page='story_reveal', return_area=RETURN_AREA)
        with self.assertRaisesRegex(ScriptEnd, 'no_supported_action_timeout'):
            self.run_task()
        self.task.device.click.assert_not_called()

    def test_observe_only_never_clicks_a_recognized_story_bubble(self):
        self.task.config.newbie_leveling.leveling_config.observe_only = True
        self.task.config.newbie_leveling.leveling_config.session_minutes = 1
        self.default_visual = self.courtyard(area=AREA)
        with self.assertRaisesRegex(ScriptEnd, 'session_limit'):
            self.run_task()
        self.task.device.click.assert_not_called()

    def test_checkpoint_survives_interruption_after_level_confirmation(self):
        self.default_visual = self.courtyard()
        ordinary_sleep = self.clock.sleep

        def interrupted_sleep(seconds):
            ordinary_sleep(seconds)
            if self.vision.observe.call_count == 2:
                raise KeyboardInterrupt('offline user stop')

        self.clock.sleep = interrupted_sleep
        with self.assertRaises(KeyboardInterrupt):
            self.run_task()
        self.task.device.click.assert_not_called()
        checkpoint = self.checkpoint()
        self.assertEqual(checkpoint['confirmed_level'], 3)
        self.assertEqual(checkpoint['character_id'], '测试角色土')
        self.assertFalse(checkpoint['completed'])
        self.assertFalse(list(self.output.glob('*.tmp')))

    def test_session_loss_saves_state_and_pauses_without_relogin(self):
        self.default_visual = self.courtyard()

        def screenshot():
            if self.screenshot_count == 2:
                raise GameSessionExpiredError('offline remote login')
            return self.screenshot()

        self.task.device.screenshot.side_effect = screenshot
        with self.assertRaisesRegex(ScriptEnd, 'capture_or_session_error'):
            self.run_task()
        self.task.device.click.assert_not_called()
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)
        self.assertEqual(self.status()['status'], 'needs_attention')

    def test_game_stuck_capture_saves_state_and_stops_instead_of_recovery(self):
        self.default_visual = self.courtyard()

        def screenshot():
            if self.screenshot_count == 2:
                raise GameStuckError('offline stuck capture')
            return self.screenshot()

        self.task.device.screenshot.side_effect = screenshot
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.task.device.click.assert_not_called()
        self.assertEqual(self.checkpoint()['confirmed_level'], 3)
        self.assertEqual(self.status()['status'], 'needs_attention')

    def test_control_failure_updates_status_and_preserves_progress_without_retry(self):
        errors = (GameSessionExpiredError, GameStuckError, GameNotRunningError,
                  GameTooManyClickError, RequestHumanTakeover)
        for index, error_type in enumerate(errors):
            with self.subTest(error=error_type.__name__):
                if index:
                    self.setUp()
                self.output.mkdir()
                ScriptTask._write_json(self.output / 'status.json', {
                    'status': 'completed', 'reason': 'stale_offline_status',
                })
                self.default_visual = self.courtyard(area=AREA)
                self.task.device.click.side_effect = error_type('offline control guard failed')
                reason = 'control_or_session_error:' + error_type.__name__
                with self.assertRaisesRegex(ScriptEnd, reason):
                    self.run_task()
                self.assertEqual(self.status()['status'], 'needs_attention')
                self.assertEqual(self.status()['reason'], reason)
                self.assertEqual(self.checkpoint()['confirmed_level'], 3)
                self.assertEqual(self.task.device.click.call_count, 1)
                self.assertEqual(self.task.device.screenshot.call_count, 2)
                self.assertIsNone(self.task._pending)
                self.assertTrue(list(self.output.glob('*-paused.png')))

    def test_invalidated_level_rechecks_then_requires_two_live_target_samples(self):
        eye = VisionObservation(page='story_eye', return_area=RETURN_AREA, tutorial_area=EYE_AREA)
        self.visuals = [self.courtyard(level=29), self.courtyard(level=29),
                        self.courtyard(level=30), eye, eye,
                        self.courtyard(level=30), self.courtyard(level=30)]
        click_frames = []
        self.task.device.click.side_effect = lambda *args, **kwargs: click_frames.append(self.vision.observe.call_count)
        with self.assertRaisesRegex(ScriptEnd, 'target_reached'):
            self.run_task()
        self.task.device.click.assert_called_once_with(
            RETURN_AREA[0] + RETURN_AREA[2] // 2, RETURN_AREA[1] + RETURN_AREA[3] // 2,
            control_name='NEWBIE_RECHECK_ACCOUNT')
        self.assertEqual(click_frames, [5])
        self.assertEqual(self.vision.observe.call_count, 7)
        self.assertEqual(self.status()['status'], 'completed')
        self.assertEqual(self.checkpoint()['confirmed_level'], 30)
        self.assertEqual(self.task.session.return_count, 1)
        self.assertEqual(self.task.session.stamina_spent, 0)

    def test_one_live_target_sample_after_recheck_does_not_complete(self):
        eye = VisionObservation(page='story_eye', return_area=RETURN_AREA, tutorial_area=EYE_AREA)
        self.visuals = [self.courtyard(level=29), self.courtyard(level=29),
                        self.courtyard(level=30), eye, eye, self.courtyard(level=30)]
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.assertEqual([item.kwargs['control_name'] for item in self.task.device.click.call_args_list],
                         ['NEWBIE_RECHECK_ACCOUNT'])
        self.assertEqual(self.status()['status'], 'needs_attention')
        self.assertEqual(self.checkpoint()['confirmed_level'], 29)
        self.assertFalse(self.checkpoint()['completed'])
        self.assertFalse(self.task.session.level_verified)

    def test_invalidated_level_without_return_or_on_unknown_page_never_clicks_tutorial(self):
        self.visuals = [self.courtyard(level=29), self.courtyard(level=29), self.courtyard(level=30),
                        VisionObservation(page='story_eye', tutorial_area=EYE_AREA),
                        VisionObservation(page='story_eye', tutorial_area=EYE_AREA)]
        self.default_visual = VisionObservation(page='unknown', return_area=RETURN_AREA,
                                               tutorial_area=EYE_AREA)
        with self.assertRaises(ScriptEnd):
            self.run_task()
        self.task.device.click.assert_not_called()

    def test_recheck_cannot_repeat_same_page_after_courtyard_revalidation(self):
        eye = VisionObservation(page='story_eye', return_area=RETURN_AREA, tutorial_area=EYE_AREA)
        self.visuals = [self.courtyard(level=29), self.courtyard(level=29),
                        self.courtyard(level=30), eye, eye,
                        self.courtyard(level=29), self.courtyard(level=29),
                        self.courtyard(level=30), eye, eye]
        with self.assertRaisesRegex(ScriptEnd, 'story_return_already_attempted'):
            self.run_task()
        self.assertEqual([item.kwargs['control_name'] for item in self.task.device.click.call_args_list],
                         ['NEWBIE_RECHECK_ACCOUNT'])
        self.assertEqual(self.task.session.return_count, 1)
        self.assertFalse(self.checkpoint()['completed'])

    def test_recheck_control_error_saves_pause_and_does_not_retry(self):
        eye = VisionObservation(page='story_eye', return_area=RETURN_AREA, tutorial_area=EYE_AREA)
        self.visuals = [self.courtyard(level=29), self.courtyard(level=29),
                        self.courtyard(level=30), eye, eye]
        self.task.device.click.side_effect = RequestHumanTakeover('offline return control rejected')
        with self.assertRaisesRegex(ScriptEnd, 'control_or_session_error:RequestHumanTakeover'):
            self.run_task()
        self.assertEqual(self.task.device.click.call_count, 1)
        self.assertIsNone(self.task._pending)
        self.assertEqual(self.status()['status'], 'needs_attention')
        self.assertEqual(self.checkpoint()['confirmed_level'], 29)
        self.assertEqual(self.task.session.return_count, 1)

    def test_executor_recheck_requires_policy_consumed_return_state(self):
        self.task.session = SessionState(started_at=100.0)
        self.task._finish = Mock(side_effect=ScriptEnd('offline rejected execution'))
        eye = VisionObservation(page='story_eye', return_area=RETURN_AREA)
        with self.assertRaises(ScriptEnd):
            self.task._execute('recheck_account', RETURN_AREA, eye)
        self.task._finish.assert_called_once()
        self.task.device.click.assert_not_called()


class NewbieSchedulerTests(unittest.TestCase):
    def scheduler(self):
        scheduler = object.__new__(Script)
        scheduler.__dict__['config'] = Mock()
        scheduler.__dict__['device'] = Mock()
        scheduler._try_acquire_queue_token = Mock(return_value=True)
        scheduler.instance_guard = None
        scheduler.config_name = 'oas_leveling'
        scheduler.save_error_log = Mock()
        scheduler.exception_handler = Mock()
        return scheduler

    def test_script_end_is_normal_stop_without_restart_or_task_retry(self):
        scheduler = self.scheduler()
        task = Mock()
        task.run.side_effect = ScriptEnd('unknown_page_timeout')
        with patch(RUNNER + '.ScriptTask', return_value=task) as task_class, patch('script.logger'):
            self.assertTrue(scheduler.run('NewbieLeveling'))
        self.assertTrue(scheduler._script_end_requested)
        scheduler.config.task_call.assert_not_called()
        scheduler.exception_handler.assert_not_called()
        scheduler.device.click.assert_not_called()
        scheduler.device.app_stop.assert_not_called()
        scheduler.device.app_start.assert_not_called()
        task.run.assert_called_once()
        task_class.assert_called_once_with(config=scheduler.config, device=scheduler.device)

    def test_wrong_binding_is_rejected_before_any_device_is_constructed(self):
        scheduler = self.scheduler()
        del scheduler.__dict__['device']
        config = scheduler.config
        config.config_name = 'oas_leveling'
        config.script.device.serial = '127.0.0.1:16384'
        config.script.device.handle = EXPECTED_HANDLE
        config.script.device.emulatorinfo_name = EXPECTED_VM
        with patch('tasks.NewbieLeveling.device.LevelingDevice') as leveling_device, \
                patch('module.device.device.Device') as generic_device, \
                patch.object(ScriptTask, 'run') as task_run, patch('script.logger'):
            self.assertTrue(scheduler.run('NewbieLeveling'))
        leveling_device.assert_not_called()
        generic_device.assert_not_called()
        task_run.assert_not_called()
        config.task_call.assert_not_called()
        self.assertNotIn('device', scheduler.__dict__)
        self.assertTrue(scheduler._script_end_requested)

    def test_newbie_has_no_generic_pre_task_screenshot_or_restart_path(self):
        for error_type in (GameStuckError, GameNotRunningError):
            with self.subTest(error=error_type.__name__):
                scheduler = self.scheduler()
                scheduler.device.screenshot.side_effect = error_type('offline capture failure')
                task = Mock()
                task.run.side_effect = ScriptEnd('runner owns capture')
                with patch(RUNNER + '.ScriptTask', return_value=task), \
                        patch('script.load_module') as loader, patch('script.logger'):
                    scheduler.run('NewbieLeveling')
                scheduler.device.screenshot.assert_not_called()
                scheduler.config.task_call.assert_not_called()
                scheduler.exception_handler.assert_not_called()
                self.assertTrue(getattr(scheduler, '_script_end_requested', False))
                loader.assert_not_called()
                scheduler._try_acquire_queue_token.assert_not_called()
                task.run.assert_called_once()

    def test_newbie_device_error_inside_task_does_not_schedule_global_restart(self):
        scheduler = self.scheduler()
        task = Mock()
        task.run.side_effect = GameStuckError('offline in-task capture failure')
        with patch(RUNNER + '.ScriptTask', return_value=task), patch('script.logger'):
            scheduler.run('NewbieLeveling')
        scheduler.config.task_call.assert_not_called()
        scheduler.exception_handler.assert_not_called()
        self.assertTrue(getattr(scheduler, '_script_end_requested', False))
        task.run.assert_called_once()

    def test_newbie_unhandled_session_loss_never_enters_global_login_handler(self):
        scheduler = self.scheduler()
        task = Mock()
        task.run.side_effect = GameSessionExpiredError('offline session error')
        with patch(RUNNER + '.ScriptTask', return_value=task), patch('script.logger'), \
                patch('tasks.Restart.login.LoginHandler') as login:
            scheduler.run('NewbieLeveling')
        login.assert_not_called()
        scheduler.config.task_call.assert_not_called()
        self.assertTrue(getattr(scheduler, '_script_end_requested', False))
        task.run.assert_called_once()


class NewbieDeviceTests(unittest.TestCase):
    def test_recovery_methods_reject_without_calling_underlying_device(self):
        # Bypass __init__: its connection setup is deliberately not exercised.
        device = object.__new__(LevelingDevice)
        for method_name in ('emulator_start', 'app_start', 'app_stop'):
            with self.subTest(method=method_name):
                with patch.object(Device, method_name) as underlying:
                    with self.assertRaises(RequestHumanTakeover):
                        getattr(device, method_name)()
                underlying.assert_not_called()


if __name__ == '__main__':
    unittest.main()
