"""Offline tests only: toolkit/python.exe -m unittest dev_tools.test_newbie_leveling_policy."""

import unittest
from dataclasses import replace
from pydantic import ValidationError

from tasks.NewbieLeveling.config import LevelingConfig, NewbieLeveling
from tasks.NewbieLeveling.policy import (
    EXPECTED_HANDLE, EXPECTED_SERIAL, EXPECTED_VM, Observation, Progress,
    SessionState, checkpoint_from_dict, checkpoint_to_dict, evaluate,
    CINEMATIC_WAIT_TIMEOUT_SECONDS,
)


class LevelingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = LevelingConfig(observe_only=False)
        self.progress = Progress()
        self.session = SessionState(started_at=100.0)

    def step(self, now=100.0, **kwargs):
        actual_serial = kwargs.pop('actual_serial', EXPECTED_SERIAL)
        observation = Observation(**kwargs)
        decision = evaluate(self.config, self.progress, self.session, observation, now,
                            actual_serial, EXPECTED_HANDLE, EXPECTED_VM)
        self.progress, self.session = decision.progress, decision.session
        return decision

    def verified(self):
        self.step(level=3, character_id='测试角色', page='courtyard')
        return self.step(now=101.0, level=3, character_id='测试角色', page='courtyard')

    def test_safe_config_defaults_and_bounds(self):
        config = NewbieLeveling()
        self.assertFalse(config.scheduler.enable)
        self.assertTrue(config.leveling_config.observe_only)
        self.assertEqual(config.leveling_config.target_level, 30)
        for changes in ({'target_level': 31}, {'stamina_budget': -1}, {'level_confirmations': 1}):
            with self.assertRaises(ValidationError):
                LevelingConfig(**changes)

    def test_wrong_instance_stops(self):
        result = self.step(actual_serial='127.0.0.1:16384')
        self.assertEqual(result.reason, 'instance_mismatch')
        self.assertTrue(result.capture_evidence)

    def test_changing_config_cannot_allow_first_instance(self):
        self.config.expected_serial = '127.0.0.1:16384'
        self.assertEqual(self.step(actual_serial='127.0.0.1:16384').action, 'stop')

    def test_checkpoint_does_not_verify_identity(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 3)
        result = self.step(level=3, page='story', safe_action='story_next', action_cost=0)
        self.assertEqual(result.reason, 'identity_unverified')

    def test_unverified_story_session_may_return_once_without_trusting_checkpoint(self):
        old_progress = Progress(EXPECTED_SERIAL, '旧角色', 30, True)
        self.progress = old_progress
        result = self.step(page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertEqual(result.safe_action, 'return_to_courtyard')
        self.assertTrue(result.session.return_attempted)
        self.assertFalse(result.session.identity_verified)
        self.assertFalse(result.session.level_verified)
        self.assertEqual(result.session.stamina_spent, 0)
        self.assertEqual(result.progress, old_progress)

    def test_second_return_in_same_session_stops_even_after_interval(self):
        self.step(page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        result = self.step(now=103.0, page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.action, 'stop')
        self.assertEqual(result.reason, 'story_return_already_attempted')
        self.assertTrue(result.capture_evidence)

    def test_return_can_cross_two_supported_pages_but_not_a_third(self):
        first = self.step(page='story_dialogue', safe_action='return_to_courtyard', action_cost=0)
        second = self.step(now=103.0, page='story_eye', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(first.action, 'execute')
        self.assertEqual(second.action, 'execute')
        self.assertEqual(second.session.return_pages, ('story_dialogue', 'story_eye'))
        self.assertEqual(second.session.return_count, 2)
        self.assertFalse(second.session.identity_verified)
        third = self.step(now=106.0, page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(third.reason, 'story_return_limit')

    def test_reveal_return_shares_the_session_budget_and_requires_live_identity(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 3)
        first = self.step(page='story_reveal', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(first.action, 'execute')
        self.assertFalse(first.session.identity_verified)
        second = self.step(now=103.0, page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(second.action, 'execute')
        repeated = self.step(now=106.0, page='story_reveal', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(repeated.reason, 'story_return_already_attempted')
        limited = self.step(now=107.0, page='story_eye', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(limited.reason, 'story_return_limit')

    def test_reveal_return_cannot_gain_a_third_attempt_from_a_new_page(self):
        self.step(page='story_dialogue', safe_action='return_to_courtyard', action_cost=0)
        self.step(now=103.0, page='story_eye', safe_action='return_to_courtyard', action_cost=0)
        result = self.step(now=106.0, page='story_reveal', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.reason, 'story_return_limit')

    def test_reveal_recheck_consumes_same_return_budget_and_invalidates_trust(self):
        self.verified()
        result = self.step(now=103.0, page='story_reveal', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertEqual(result.session.return_pages, ('story_reveal',))
        self.assertEqual(result.session.return_count, 1)
        self.assertFalse(result.session.identity_verified)
        self.assertFalse(result.session.level_verified)
        result = self.step(now=106.0, page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertEqual(result.session.return_count, 2)

    def test_reveal_question_or_recheck_cannot_bypass_first_target_read(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 29)
        self.step(page='courtyard', character_id='测试角色', level=29)
        self.step(now=101.0, page='courtyard', level=29)
        result = self.step(now=103.0, page='story_reveal', level=30, safe_action='story_npc', action_cost=0)
        self.assertEqual(result.reason, 'target_level_pending_confirmation')
        result = self.step(now=104.0, page='story_reveal', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.reason, 'recheck_live_account')
        self.assertFalse(result.progress.completed)
        self.assertFalse(result.session.identity_verified)
        self.step(now=105.0, page='courtyard', character_id='测试角色', level=30)
        self.step(now=106.0, page='courtyard', level=30)
        result = self.step(now=108.0, page='story_reveal', safe_action='story_npc', action_cost=0)
        self.assertEqual(result.action, 'complete')

    def test_return_cannot_loop_back_to_a_previously_used_page(self):
        self.step(page='story_dialogue', safe_action='return_to_courtyard', action_cost=0)
        self.step(now=103.0, page='story_eye', safe_action='return_to_courtyard', action_cost=0)
        result = self.step(now=106.0, page='story_dialogue', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.reason, 'story_return_already_attempted')

    def test_story_return_observe_only_never_consumes_an_attempt(self):
        self.config.observe_only = True
        result = self.step(page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.action, 'observe')
        self.assertFalse(result.session.return_attempted)
        self.assertIsNone(result.session.last_action_at)
        result = self.step(now=130.0, page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.reason, 'identity_unverified_timeout')

    def test_story_return_requires_the_exact_verified_scene(self):
        for page in ('unknown', 'courtyard', 'battle', ''):
            with self.subTest(page=page):
                result = self.step(page=page, safe_action='return_to_courtyard', action_cost=0)
                self.assertEqual(result.action, 'stop')
                self.assertFalse(result.session.return_attempted)

    def test_story_return_cannot_override_wrong_device(self):
        result = self.step(page='story_scene', safe_action='return_to_courtyard', action_cost=0,
                           actual_serial='127.0.0.1:16384')
        self.assertEqual(result.reason, 'instance_mismatch')
        self.assertFalse(result.session.return_attempted)

    def test_story_return_requires_zero_integer_cost_not_missing_or_boolean(self):
        for cost in (None, False, -1, 1):
            with self.subTest(cost=cost):
                result = self.step(page='story_scene', safe_action='return_to_courtyard', action_cost=cost)
                self.assertEqual(result.reason, 'story_return_must_be_explicitly_free')
                self.assertFalse(result.session.return_attempted)

    def test_story_return_respects_interval_and_existing_unknown_deadline(self):
        self.session = replace(self.session, last_action_at=99.0, unknown_since=90.0)
        result = self.step(page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.reason, 'action_interval')
        self.assertFalse(result.session.return_attempted)
        self.assertEqual(result.session.unknown_since, 90.0)
        result = self.step(now=120.0, page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.reason, 'identity_unverified_timeout')
        self.assertFalse(result.session.return_attempted)

    def test_story_return_does_not_enable_any_other_unverified_action(self):
        self.step(page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        result = self.step(now=103.0, page='story_scene', safe_action='story_npc', action_cost=0)
        self.assertEqual(result.reason, 'identity_unverified')
        result = self.step(now=130.0, page='unknown')
        self.assertEqual(result.reason, 'identity_unverified_timeout')

    def test_verified_session_cannot_use_return_exception(self):
        self.verified()
        result = self.step(now=103.0, page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.reason, 'forbidden_action')

    def test_return_scene_cannot_supply_inconsistent_level_or_identity(self):
        for account_data in ({'level': 30}, {'level': 0}, {'character_id': '未知角色'}):
            with self.subTest(account_data=account_data):
                result = self.step(page='story_scene', safe_action='return_to_courtyard',
                                   action_cost=0, **account_data)
                self.assertEqual(result.reason, 'unexpected_account_data_on_story_return')
                self.assertFalse(result.session.return_attempted)
                self.assertFalse(result.session.identity_verified)

    def test_verified_identity_and_level_allow_free_story_npc_in_scene(self):
        self.verified()
        result = self.step(now=103.0, page='story_scene', safe_action='story_npc', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertFalse(result.session.return_attempted)

    def test_free_dialogue_skip_and_eye_target_require_verified_session(self):
        for page, action in (('story_dialogue', 'story_skip'), ('story_eye', 'tutorial_target')):
            self.setUp()
            self.assertNotEqual(self.step(page=page, safe_action=action, action_cost=0).action, 'execute')
            self.verified()
            self.assertEqual(self.step(now=104.0, page=page, safe_action=action, action_cost=0).action, 'execute')

    def test_recheck_clears_live_trust_preserves_progress_and_blocks_other_actions(self):
        self.verified()
        trusted_progress = self.progress
        result = self.step(now=103.0, page='story_dialogue', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertFalse(result.session.identity_verified)
        self.assertFalse(result.session.level_verified)
        self.assertEqual(result.session.character_id, '')
        self.assertIsNone(result.session.candidate_level)
        self.assertEqual(result.session.candidate_count, 0)
        self.assertEqual(result.progress, trusted_progress)
        self.assertEqual(result.session.return_count, 1)
        self.assertEqual(result.session.stamina_spent, 0)
        for action in ('story_skip', 'tutorial_target', 'battle_prepare'):
            blocked = self.step(now=105.0, page='story_eye', safe_action=action, action_cost=0, stamina=100)
            self.assertEqual(blocked.reason, 'identity_unverified')
        returned = self.step(now=106.0, page='story_eye', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(returned.action, 'execute')
        self.assertEqual(returned.session.return_count, 2)
        self.assertFalse(returned.session.identity_verified)

    def test_recheck_requires_fresh_courtyard_identity_and_two_level_samples(self):
        self.verified()
        self.step(now=103.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        result = self.step(now=106.0, page='courtyard', character_id='测试角色', level=3,
                           safe_action='story_npc', action_cost=0)
        self.assertNotEqual(result.action, 'execute')
        self.assertEqual(result.reason, 'level_unverified')
        result = self.step(now=107.0, page='courtyard', character_id='测试角色', level=3,
                           safe_action='story_npc', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertEqual(result.session.return_count, 1)

    def test_recheck_cannot_repeat_after_courtyard_revalidation(self):
        self.verified()
        self.step(now=103.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.step(now=106.0, page='courtyard', character_id='测试角色', level=3)
        self.step(now=107.0, page='courtyard', character_id='测试角色', level=3)
        result = self.step(now=110.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.reason, 'story_return_already_attempted')

    def test_recheck_observe_only_does_not_clear_live_identity_or_consume_return(self):
        self.verified()
        self.config.observe_only = True
        result = self.step(now=103.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.action, 'observe')
        self.assertTrue(result.session.identity_verified)
        self.assertTrue(result.session.level_verified)
        self.assertEqual(result.session.return_count, 0)
        self.assertFalse(result.session.return_attempted)

    def test_recheck_rejects_unverified_session_unsupported_page_and_nonzero_cost(self):
        self.assertEqual(self.step(page='story_eye', safe_action='recheck_account', action_cost=0).reason,
                         'identity_unverified')
        self.verified()
        result = self.step(now=103.0, page='courtyard', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.reason, 'recheck_requires_verified_story_page')
        for cost in (None, False, 1):
            result = self.step(now=104.0, page='story_eye', safe_action='recheck_account', action_cost=cost)
            self.assertEqual(result.reason, 'account_recheck_must_be_explicitly_free')
        self.assertTrue(self.session.identity_verified)
        self.assertEqual(self.session.return_count, 0)

    def test_recheck_does_not_bypass_first_target_read_or_confirmed_target(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 29)
        self.step(page='courtyard', character_id='测试角色', level=29)
        self.step(now=101.0, page='courtyard', level=29)
        pending = self.step(now=103.0, page='story_eye', level=30, safe_action='recheck_account', action_cost=0)
        self.assertEqual(pending.reason, 'target_level_pending_confirmation')
        self.assertFalse(pending.session.return_attempted)
        missing = self.step(now=104.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(missing.reason, 'recheck_live_account')
        self.assertFalse(missing.progress.completed)
        self.assertFalse(missing.session.level_verified)
        first = self.step(now=105.0, page='courtyard', character_id='测试角色', level=30)
        self.assertNotEqual(first.action, 'complete')
        self.assertEqual(self.step(now=106.0, page='courtyard', level=30).action, 'complete')
        terminal = self.step(now=109.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(terminal.action, 'complete')
        self.assertEqual(terminal.session.return_count, 1)

    def test_invalidated_level_can_recheck_without_allowing_story_or_new_battles(self):
        self.verified()
        self.session = replace(self.session, level_verified=False, candidate_level=None,
                               candidate_count=0, last_level_sample_at=None)
        previous = self.progress
        for action in ('story_npc', 'story_skip', 'tutorial_target', 'battle_prepare',
                       'start_exploration', 'start_experience'):
            with self.subTest(action=action):
                result = self.step(now=103.0, page='story_eye', safe_action=action,
                                   action_cost=0, stamina=100)
                self.assertEqual(result.reason, 'level_unverified')
        result = self.step(now=104.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertEqual(result.progress, previous)
        self.assertFalse(result.session.identity_verified)
        self.assertFalse(result.session.level_verified)
        self.assertEqual(result.session.return_count, 1)
        self.assertEqual(result.session.stamina_spent, 0)
        blocked = self.step(now=107.0, page='story_scene', safe_action='story_npc', action_cost=0)
        self.assertEqual(blocked.reason, 'identity_unverified')

    def test_invalidated_recheck_rejects_cost_page_identity_and_return_budget(self):
        self.verified()
        self.session = replace(self.session, level_verified=False)
        for page in ('unknown', 'courtyard', 'battle'):
            with self.subTest(page=page):
                result = self.step(now=103.0, page=page, safe_action='recheck_account', action_cost=0)
                self.assertEqual(result.reason, 'recheck_requires_verified_story_page')
        for cost in (None, False, -1, 1):
            with self.subTest(cost=cost):
                result = self.step(now=103.0, page='story_eye', safe_action='recheck_account', action_cost=cost)
                self.assertEqual(result.reason, 'account_recheck_must_be_explicitly_free')
        result = self.step(now=103.0, page='story_eye', safe_action='recheck_account', action_cost=0,
                           character_id='其他角色')
        self.assertEqual(result.reason, 'character_changed_during_session')
        self.session = replace(self.session, return_attempted=True,
                               return_pages=('story_dialogue', 'story_scene'), return_count=2)
        result = self.step(now=103.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.reason, 'story_return_limit')
        self.assertTrue(result.session.identity_verified)

    def test_invalidated_recheck_honors_interval_observe_only_and_unknown_deadline(self):
        self.verified()
        self.session = replace(self.session, level_verified=False, last_action_at=102.5,
                               unknown_since=101.0)
        result = self.step(now=103.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.reason, 'action_interval')
        self.assertFalse(result.session.return_attempted)
        self.config.observe_only = True
        result = self.step(now=106.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.action, 'observe')
        self.assertTrue(result.session.identity_verified)
        self.assertFalse(result.session.level_verified)
        self.assertEqual(result.session.return_count, 0)
        result = self.step(now=131.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.reason, 'level_unverified_timeout')

    def test_completed_checkpoint_can_navigate_to_recheck_but_needs_live_double_level(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 30, True)
        first = self.step(page='courtyard', character_id='测试角色')
        self.assertEqual(first.reason, 'completed_checkpoint_needs_live_level')
        returned = self.step(now=103.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(returned.action, 'execute')
        self.assertFalse(returned.session.identity_verified)
        self.assertFalse(returned.session.level_verified)
        unbound = self.step(now=106.0, page='courtyard', level=30)
        self.assertEqual(unbound.reason, 'identity_unverified')
        one = self.step(now=107.0, page='courtyard', character_id='测试角色', level=30)
        self.assertNotEqual(one.action, 'complete')
        two = self.step(now=108.0, page='courtyard', character_id='测试角色', level=30)
        self.assertEqual(two.action, 'complete')

    def test_recheck_honors_action_interval_and_cannot_supply_account_data(self):
        self.verified()
        self.step(now=103.0, page='story_eye', safe_action='tutorial_target', action_cost=0)
        result = self.step(now=104.0, page='story_eye', safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.reason, 'action_interval')
        self.assertTrue(result.session.identity_verified)
        result = self.step(now=106.0, page='story_eye', level=3, safe_action='recheck_account', action_cost=0)
        self.assertEqual(result.reason, 'unexpected_account_data_on_recheck')

    def test_unknown_level_is_not_zero(self):
        result = self.step(character_id='测试角色', page='courtyard')
        self.assertIsNone(result.progress.confirmed_level)
        self.assertFalse(result.session.level_verified)

    def test_confirmations_require_separate_times(self):
        self.step(level=3, character_id='测试角色')
        self.step(level=3, character_id='测试角色')
        self.assertFalse(self.session.level_verified)
        self.step(now=101.0, level=3)
        self.assertEqual(self.progress.confirmed_level, 3)

    def test_missing_reading_breaks_consecutive_confirmation(self):
        self.step(level=3, character_id='测试角色')
        self.step(now=101.0)
        self.step(now=102.0, level=3)
        self.assertFalse(self.session.level_verified)

    def test_zero_cost_story_can_run_without_stamina_or_repeated_identity(self):
        self.verified()
        result = self.step(now=102.0, page='story', safe_action='story_next', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertEqual(result.session.stamina_spent, 0)

    def test_observe_only_never_executes(self):
        self.config.observe_only = True
        self.verified()
        result = self.step(now=102.0, page='story', safe_action='story_next', action_cost=0)
        self.assertEqual(result.action, 'observe')
        self.assertIsNone(result.session.last_action_at)

    def test_purchase_summon_and_lineup_not_whitelisted(self):
        self.verified()
        for action in ('purchase_stamina', 'summon', 'switch_soul', 'replace_shikigami'):
            self.assertEqual(self.step(now=102.0, page='story', safe_action=action,
                                       action_cost=0).reason, 'forbidden_action')

    def test_unknown_pages_stop_after_timeout(self):
        self.verified()
        self.assertNotEqual(self.step(now=102.0).action, 'stop')
        result = self.step(now=131.0)
        self.assertEqual(result.action, 'stop')
        self.assertTrue(result.capture_evidence)

    def test_initial_target_needs_two_readings(self):
        self.assertNotEqual(self.step(level=30, character_id='测试角色').action, 'complete')
        self.assertEqual(self.step(now=101.0, level=30).action, 'complete')

    def test_implausible_target_jump_stops_without_completion(self):
        self.verified()
        result = self.step(now=102.0, level=30)
        self.assertEqual(result.reason, 'implausible_level_jump')
        self.assertFalse(result.progress.completed)

    def test_target_transition_blocks_immediately_then_completes(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 29)
        self.step(level=29, character_id='测试角色')
        self.step(now=101.0, level=29)
        result = self.step(now=102.0, level=30, page='story', safe_action='story_next', action_cost=0)
        self.assertNotEqual(result.action, 'execute')
        self.assertEqual(self.step(now=103.0, level=30).action, 'complete')

    def test_target_cannot_reuse_confirmations_from_previous_level(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 29)
        self.step(level=29, character_id='测试角色')
        self.step(now=101.0, level=29)
        self.assertNotEqual(self.step(now=101.1, level=30).action, 'complete')

    def test_unconfirmed_target_followed_by_missing_level_blocks_actions(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 29)
        self.step(level=29, character_id='测试角色')
        self.step(now=101.0, level=29)
        self.step(now=102.0, level=30)
        result = self.step(now=103.0, page='story', safe_action='story_next', action_cost=0)
        self.assertNotEqual(result.action, 'execute')

    def test_different_new_character_cannot_inherit_completion(self):
        self.progress = Progress(EXPECTED_SERIAL, '旧角色', 30, True)
        result = self.step(level=3, character_id='新角色')
        self.assertEqual(result.progress.character_id, '新角色')
        self.assertFalse(result.progress.completed)
        self.assertIsNone(result.progress.confirmed_level)

    def test_same_session_character_change_stops(self):
        self.verified()
        self.assertEqual(self.step(now=102.0, character_id='另一个角色').reason,
                         'character_changed_during_session')

    def test_pinned_character_is_enforced(self):
        self.config.character_id = '指定角色'
        self.assertEqual(self.step(character_id='其他角色').reason, 'configured_character_mismatch')

    def test_stamina_unknown_blocks_even_zero_cost_battle_start(self):
        self.verified()
        result = self.step(now=102.0, page='battle_prepare', safe_action='battle_prepare', action_cost=0)
        self.assertEqual(result.reason, 'stamina_unverified')

    def test_missing_cost_does_not_default_to_free(self):
        self.verified()
        result = self.step(now=102.0, page='story', safe_action='story_next')
        self.assertEqual(result.reason, 'action_cost_unverified')

    def test_story_actions_must_be_explicitly_free(self):
        self.verified()
        result = self.step(now=102.0, page='story', safe_action='story_next',
                           action_cost=1, stamina=100)
        self.assertEqual(result.reason, 'non_battle_action_must_be_free')

    def test_budget_reserved_and_next_battle_needs_level_recheck(self):
        self.verified()
        result = self.step(now=102.0, page='exploration', safe_action='start_exploration',
                           action_cost=3, stamina=20)
        self.assertEqual(result.action, 'execute')
        self.assertEqual(result.session.stamina_spent, 3)
        self.assertFalse(result.session.level_verified)
        self.assertNotEqual(self.step(now=104.0, page='exploration', safe_action='start_exploration',
                                      action_cost=3, stamina=17).action, 'execute')

    def test_in_progress_battle_can_finish_without_visible_level(self):
        self.verified()
        self.step(now=102.0, page='exploration', safe_action='start_exploration',
                  action_cost=3, stamina=20)
        self.assertEqual(self.step(now=104.0, page='battle', safe_action='battle_auto',
                                   action_cost=0).action, 'execute')
        self.assertEqual(self.step(now=106.0, page='battle_settlement',
                                   safe_action='battle_settlement', action_cost=0).action, 'execute')
        self.assertFalse(self.session.level_verified)

    def test_budget_and_insufficient_stamina_stop(self):
        self.verified()
        self.config.stamina_budget = 2
        self.assertEqual(self.step(now=102.0, page='exploration', safe_action='start_exploration',
                                   action_cost=3, stamina=20).reason, 'stamina_budget_exhausted')
        self.config.stamina_budget = 60
        self.assertEqual(self.step(now=103.0, page='exploration', safe_action='start_exploration',
                                   action_cost=3, stamina=2).reason, 'insufficient_stamina')

    def test_action_interval(self):
        self.verified()
        self.step(now=102.0, page='story', safe_action='story_next', action_cost=0)
        self.assertEqual(self.step(now=103.0, page='story', safe_action='story_next', action_cost=0).reason,
                         'action_interval')

    def test_session_is_bounded(self):
        self.assertEqual(self.step(now=1300.0).reason, 'session_limit')

    def test_cinematic_unverified_identity_waits_passively_up_to_ninety_seconds(self):
        self.assertEqual(CINEMATIC_WAIT_TIMEOUT_SECONDS, 90)
        self.progress = Progress(EXPECTED_SERIAL, '旧角色', 30, True)
        for now in (100.0, 130.0, 160.0, 189.0):
            result = self.step(now=now, page='story_cinematic_wait')
            self.assertEqual(result.action, 'wait')
            self.assertIsNone(result.safe_action)
            self.assertFalse(result.session.identity_verified)
            self.assertIsNone(result.session.last_action_at)
            self.assertEqual(result.session.cinematic_since, 100.0)
            self.assertIsNone(result.session.unknown_since)
        result = self.step(now=190.0, page='story_cinematic_wait')
        self.assertEqual(result.action, 'stop')
        self.assertTrue(result.capture_evidence)
        self.assertFalse(result.session.return_attempted)

    def test_cinematic_verified_session_keeps_one_ninety_second_deadline(self):
        self.verified()
        self.session = replace(self.session, unknown_since=None)
        for now in (102.0, 132.0, 170.0, 191.0):
            result = self.step(now=now, page='story_cinematic_wait')
            self.assertEqual(result.action, 'wait')
            self.assertIsNone(result.safe_action)
            self.assertEqual(result.session.cinematic_since, 102.0)
            self.assertIsNone(result.session.unknown_since)
            self.assertEqual(result.progress.confirmed_level, 3)
        result = self.step(now=192.0, page='story_cinematic_wait')
        self.assertEqual(result.action, 'stop')
        self.assertEqual(result.reason, 'cinematic_wait_timeout')

    def test_cinematic_to_unknown_gets_an_independent_thirty_second_limit(self):
        self.step(page='story_cinematic_wait')
        self.assertEqual(self.step(now=143.0, page='story_cinematic_wait').action, 'wait')
        result = self.step(now=144.0, page='unknown')
        self.assertEqual(result.action, 'wait')
        self.assertEqual(result.session.unknown_since, 144.0)
        self.assertEqual(result.session.cinematic_since, 100.0)
        self.assertEqual(self.step(now=173.0, page='unknown').action, 'wait')
        self.assertEqual(self.step(now=174.0, page='unknown').reason, 'identity_unverified_timeout')

    def test_forty_three_second_cinematic_can_transition_to_stable_known_action(self):
        self.verified()
        previous_progress = self.progress
        self.step(now=102.0, page='story_cinematic_wait')
        self.assertEqual(self.step(now=145.0, page='story_cinematic_wait').action, 'wait')
        # The runner's first known frame does not yet have a stable candidate.
        first_scene = self.step(now=146.0, page='story_scene')
        self.assertEqual(first_scene.action, 'wait')
        self.assertEqual(first_scene.session.unknown_since, 146.0)
        second_scene = self.step(now=147.0, page='story_scene', safe_action='story_npc', action_cost=0)
        self.assertEqual(second_scene.action, 'execute')
        self.assertIsNone(second_scene.session.cinematic_since)
        self.assertIsNone(second_scene.session.unknown_since)
        self.assertEqual(second_scene.progress, previous_progress)

    def test_cinematic_unknown_flicker_cannot_extend_total_passive_time(self):
        for now, page in ((100.0, 'story_cinematic_wait'), (120.0, 'unknown'),
                          (140.0, 'story_cinematic_wait'), (150.0, 'unknown'),
                          (170.0, 'story_cinematic_wait'), (189.0, 'unknown')):
            result = self.step(now=now, page=page)
            self.assertEqual(result.action, 'wait')
            self.assertEqual(result.session.cinematic_since, 100.0)
        result = self.step(now=190.0, page='unknown')
        self.assertEqual(result.reason, 'cinematic_wait_timeout')

    def test_plain_unknown_without_cinematic_still_times_out_at_thirty_seconds(self):
        self.assertEqual(self.step(page='unknown').action, 'wait')
        self.assertEqual(self.step(now=129.0, page='unknown').action, 'wait')
        result = self.step(now=130.0, page='unknown')
        self.assertEqual(result.reason, 'identity_unverified_timeout')
        self.assertIsNone(result.session.cinematic_since)

    def test_real_npc_execute_allows_a_new_independent_cinematic_deadline(self):
        self.verified()
        self.step(now=102.0, page='story_cinematic_wait')
        result = self.step(now=146.0, page='story_scene', safe_action='story_npc', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertIsNone(result.session.cinematic_since)
        self.assertEqual(self.step(now=147.0, page='story_cinematic_wait').action, 'wait')
        result = self.step(now=236.0, page='story_cinematic_wait')
        self.assertEqual(result.action, 'wait')
        self.assertEqual(result.session.cinematic_since, 147.0)
        self.assertEqual(self.step(now=237.0, page='story_cinematic_wait').reason, 'cinematic_wait_timeout')

    def test_observe_only_known_action_does_not_reset_cinematic_deadline(self):
        self.verified()
        self.step(now=102.0, page='story_cinematic_wait')
        self.config.observe_only = True
        result = self.step(now=146.0, page='story_scene', safe_action='story_npc', action_cost=0)
        self.assertEqual(result.action, 'observe')
        self.assertEqual(result.session.cinematic_since, 102.0)
        result = self.step(now=192.0, page='story_scene', safe_action='story_npc', action_cost=0)
        self.assertEqual(result.reason, 'cinematic_wait_timeout')

    def test_bounded_return_execute_also_ends_cinematic_passive_episode(self):
        self.step(page='story_cinematic_wait')
        result = self.step(now=143.0, page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.action, 'execute')
        self.assertIsNone(result.session.cinematic_since)
        self.assertFalse(result.session.identity_verified)
        self.assertEqual(result.session.return_count, 1)

    def test_expired_cinematic_cannot_be_revived_by_a_late_return_action(self):
        self.step(page='story_cinematic_wait')
        result = self.step(now=190.0, page='story_scene', safe_action='return_to_courtyard', action_cost=0)
        self.assertEqual(result.reason, 'cinematic_wait_timeout')
        self.assertFalse(result.session.return_attempted)

    def test_cinematic_session_limit_and_instance_check_take_priority(self):
        result = self.step(now=1299.0, page='story_cinematic_wait')
        self.assertEqual(result.action, 'wait')
        self.assertEqual(self.step(now=1300.0, page='story_cinematic_wait').reason, 'session_limit')
        self.assertEqual(self.step(now=1300.0, page='story_cinematic_wait',
                                   actual_serial='127.0.0.1:16384').reason, 'instance_mismatch')

    def test_cinematic_rejects_injected_actions_with_or_without_live_identity(self):
        for verified in (False, True):
            self.setUp()
            if verified:
                self.verified()
            for action in ('story_npc', 'tutorial_target', 'return_to_courtyard',
                           'recheck_account', 'battle_auto', 'purchase_stamina'):
                with self.subTest(verified=verified, action=action):
                    result = self.step(now=103.0, page='story_cinematic_wait',
                                       safe_action=action, action_cost=0)
                    self.assertEqual(result.action, 'stop')
                    # The earlier unverified-return page guard already rejects
                    # this one action before cinematic waiting is considered.
                    expected = ('return_requires_verified_story_scene'
                                if not verified and action == 'return_to_courtyard'
                                else 'cinematic_actions_forbidden')
                    self.assertEqual(result.reason, expected)
                    self.assertIsNone(result.session.last_action_at)
                    self.assertEqual(result.session.stamina_spent, 0)

    def test_cinematic_cannot_delay_confirmed_target_completion(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 29)
        self.step(page='courtyard', character_id='测试角色', level=29)
        self.step(now=101.0, page='courtyard', level=29)
        first = self.step(now=102.0, page='story_cinematic_wait', level=30)
        self.assertEqual(first.reason, 'target_level_pending_confirmation')
        self.assertNotEqual(first.action, 'complete')
        second = self.step(now=103.0, page='story_cinematic_wait', level=30)
        self.assertEqual(second.action, 'complete')
        self.assertEqual(second.progress.confirmed_level, 30)
        self.session = replace(self.session, cinematic_since=14.0)
        terminal = self.step(now=104.0, page='story_cinematic_wait', safe_action='story_npc', action_cost=0)
        self.assertEqual(terminal.action, 'complete')
        self.assertIsNone(terminal.safe_action)

    def test_cinematic_observe_only_never_authorizes_an_action(self):
        self.config.observe_only = True
        self.assertEqual(self.step(page='story_cinematic_wait').action, 'observe')
        result = self.step(now=189.0, page='story_cinematic_wait')
        self.assertEqual(result.action, 'observe')
        self.assertIsNone(result.safe_action)
        self.assertEqual(self.step(now=190.0, page='story_cinematic_wait').action, 'stop')

    def test_level_regression_stops(self):
        self.verified()
        self.assertEqual(self.step(now=102.0, level=2).reason, 'level_regression')

    def test_checkpoint_round_trip_and_invalid_values(self):
        original = Progress(EXPECTED_SERIAL, '测试角色', 30, True)
        self.assertEqual(checkpoint_from_dict(checkpoint_to_dict(original)), original)
        for changes in ({'version': 2}, {'confirmed_level': 0}, {'confirmed_level': True},
                        {'completed': 'false'}, {'character_id': None}):
            data = {**checkpoint_to_dict(original), **changes}
            with self.assertRaises(ValueError):
                checkpoint_from_dict(data)

    def test_same_completed_character_requires_new_live_confirmation(self):
        self.progress = Progress(EXPECTED_SERIAL, '测试角色', 30, True)
        self.assertNotEqual(self.step(character_id='测试角色').action, 'complete')
        self.assertNotEqual(self.step(now=101.0, level=30).action, 'complete')
        self.assertEqual(self.step(now=102.0, level=30).action, 'complete')


if __name__ == '__main__':
    unittest.main()
