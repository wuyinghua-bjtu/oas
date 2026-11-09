"""Replay recorded game images through real vision/policy and a mocked device.

No Device is constructed, no real input is sent, and all runner output goes
to TemporaryDirectory. Account OCR is stubbed here; the vision suite separately
checks the installed local OCR against these same courtyard captures.
"""

from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from dev_tools import test_newbie_leveling_runner as harness
from module.exception import ScriptEnd
from tasks.NewbieLeveling.vision import NewbieVision


FIXTURES = Path(__file__).with_name('fixtures') / 'newbie_leveling'


class RealFrameReplayTests(unittest.TestCase):
    def test_recorded_movie_waits_over_30_seconds_then_resumes_known_npc(self):
        run = harness.NewbieRunnerTests()
        run.setUp()
        self.addCleanup(run.doCleanups)
        run.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        vision = NewbieVision(text_reader=lambda crop, field:
                              '3' if field.startswith('level') else '回放角色')
        run.vision.observe.side_effect = vision.observe

        def frame(name):
            return np.array(Image.open(FIXTURES / name).convert('RGB'))

        tanuki = frame('post_eye_tanuki/1788882324827293500-00.png')
        courtyard = frame('courtyard_1280.png')
        movie = frame('cinematic/cinematic_paused_1280.png')
        after = frame('cinematic/cinematic_post_tanuki_02_1280.png')
        # Recorded images + simulated passage of time, NOT a fresh live run.
        # Six movie samples represent >30s; no skip/action may be sent there.
        frames = ([(tanuki, 0)] * 2 + [(courtyard, 0)] * 5 +
                  [(tanuki, 0)] * 5 + [(movie, 6.5)] * 6 + [(after, 0)] * 5)
        unknown = np.zeros((720, 1280, 3), dtype=np.uint8)
        movie_click_counts = []

        def screenshot():
            current, elapsed = frames.pop(0) if frames else (unknown, 0)
            run.clock.now += elapsed
            run.task.device.image = current
            if elapsed:
                movie_click_counts.append(run.task.device.click.call_count)
            return run.screenshot()

        run.task.device.screenshot.side_effect = screenshot
        with self.assertRaises(ScriptEnd):
            run.run_task()
        self.assertEqual(movie_click_counts, [3] * 6)
        self.assertEqual([entry.kwargs['control_name']
                          for entry in run.task.device.click.call_args_list], [
            'NEWBIE_RETURN_TO_COURTYARD', 'NEWBIE_STORY_NPC',
            'NEWBIE_STORY_NPC', 'NEWBIE_STORY_NPC',
        ])
        self.assertEqual(run.checkpoint()['confirmed_level'], 3)
        self.assertEqual(run.status()['status'], 'needs_attention')
        self.assertEqual(run.status()['stamina_reserved'], 0)
        run.task.device.app_start.assert_not_called()
        run.task.device.app_stop.assert_not_called()

    def test_real_story_widgets_form_one_guarded_flow(self):
        run = harness.NewbieRunnerTests()
        run.setUp()
        self.addCleanup(run.doCleanups)
        run.task.config.newbie_leveling.leveling_config.unknown_timeout_seconds = 30
        vision = NewbieVision(text_reader=lambda crop, field:
                              '3' if field.startswith('level') else '回放角色')
        run.vision.observe.side_effect = vision.observe

        def frame(name):
            return np.array(Image.open(FIXTURES / name).convert('RGB'))

        reveal = frame('story_reveal_1280.png')
        courtyard = frame('courtyard_1280.png')
        eye = frame('story_eye_reentry_1280.png')
        dialogue = frame('dialogue_widget_cat_1280.png')
        moving_target = frame('reveal_widget_camera3_1280.png')
        kagura = frame('dialogue_widget_kagura_1280.png')
        close_eye = frame('reveal_eye_close/1788880999139126900-00.png')
        # Repeated stored frames test routing, not independence of live-frame
        # sampling. Live captures and animation holdouts have their own tests.
        frames = ([reveal] * 2 + [courtyard] * 5 + [eye] * 5 +
                  [reveal] * 5 + [dialogue] * 5 + [moving_target] * 5 +
                  [kagura] * 5 + [close_eye] * 5)
        unknown = np.zeros((720, 1280, 3), dtype=np.uint8)

        def screenshot():
            run.task.device.image = frames.pop(0) if frames else unknown
            return run.screenshot()

        run.task.device.screenshot.side_effect = screenshot
        with self.assertRaises(ScriptEnd):
            run.run_task()
        actions = [entry.kwargs['control_name']
                   for entry in run.task.device.click.call_args_list]
        self.assertEqual(actions, [
            'NEWBIE_RETURN_TO_COURTYARD', 'NEWBIE_STORY_NPC',
            'NEWBIE_TUTORIAL_TARGET', 'NEWBIE_STORY_NPC',
            'NEWBIE_STORY_SKIP', 'NEWBIE_STORY_NPC',
            'NEWBIE_STORY_SKIP', 'NEWBIE_TUTORIAL_TARGET',
        ])
        self.assertEqual(run.checkpoint()['confirmed_level'], 3)
        self.assertEqual(run.status()['status'], 'needs_attention')
        self.assertEqual(run.status()['stamina_reserved'], 0)
        run.task.device.app_start.assert_not_called()
        run.task.device.app_stop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
