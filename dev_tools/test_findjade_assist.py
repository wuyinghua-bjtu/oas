"""Offline cycle/account cache tests, with all game operations mocked."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from tasks.FindJade.assist import ensure_sender_assist, sender_battle_before
from tasks.FindJade.report import current_period, CooperationReport


class AssistCycleTests(unittest.TestCase):
    def task(self, folder, character='小号甲', server='区服甲'):
        task = Mock()
        task.support_account = SimpleNamespace(character=character, svr=server)
        task.cooperation_report = SimpleNamespace(
            directory=Path(folder), period=current_period(datetime.now()))
        task.is_in_real_battle.return_value = False
        task.battle_result_visible.return_value = False
        task.appear.return_value = True
        return task

    def cache(self, task):
        period = task.cooperation_report.period
        path = task.cooperation_report.directory / ('assist-' + period.strftime('%Y%m%d-%H%M') + '.json')
        path.write_text(json.dumps({'period':period.isoformat(), 'accounts':{
            CooperationReport.account_key(task.support_account): {'verified':True}}}), encoding='utf-8')
        return path

    def test_success_cache_skips_all_screenshots_and_game_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            task = self.task(folder)
            self.cache(task)
            ensure_sender_assist(task)
            task.screenshot.assert_not_called()
            task.device.swipe.assert_not_called()

    def test_same_character_other_server_does_not_share_cache(self):
        from tasks.FindJade.WantedQuestsEx import SenderBattleFailed
        with tempfile.TemporaryDirectory() as folder:
            self.cache(self.task(folder))
            task = self.task(folder, server='区服乙')
            task.is_in_real_battle.return_value = True
            from tasks.Component.GeneralBattle.general_battle import GeneralBattle
            with patch.object(GeneralBattle, 'battle_wait', return_value=True) as finish:
                with self.assertRaises(SenderBattleFailed):
                    ensure_sender_assist(task)
            finish.assert_called_once_with(task, False)
            task.screenshot.assert_called_once()

    def test_old_period_is_not_reused(self):
        from tasks.FindJade.WantedQuestsEx import SenderBattleFailed
        with tempfile.TemporaryDirectory() as folder:
            task = self.task(folder)
            period = task.cooperation_report.period
            with patch('tasks.FindJade.assist.datetime') as clock:
                clock.now.return_value = period - timedelta(days=1)
                with self.assertRaisesRegex(Exception, '周期已变化'):
                    ensure_sender_assist(task)
            task.screenshot.assert_not_called()

    def test_first_success_is_persisted_and_second_instance_skips(self):
        from tasks.GroupedAwakening.script_task import ScriptTask as GroupTask
        with tempfile.TemporaryDirectory() as folder:
            task = self.task(folder)
            def prepare(players, evidence, save, **kwargs):
                evidence['assist_verified'] = {task.support_account.character: True}
                evidence['assist_attempt'] = {task.support_account.character: '已确认'}
            with patch.object(GroupTask, 'prepare_assists', side_effect=prepare) as prepare_mock:
                ensure_sender_assist(task)
                second = self.task(folder)
                ensure_sender_assist(second)
            self.assertEqual(prepare_mock.call_count, 1)
            second.screenshot.assert_not_called()

    def test_failed_confirmation_never_sets_success_or_runs_normal_preparation(self):
        from tasks.GroupedAwakening.script_task import ScriptTask as GroupTask
        from tasks.FindJade.WantedQuestsEx import SenderBattleFailed
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        with tempfile.TemporaryDirectory() as folder:
            task = self.task(folder)
            with patch.object(GroupTask, 'prepare_assists') as prepare, \
                    patch.object(GeneralBattle, 'battle_before') as normal:
                with self.assertRaises(SenderBattleFailed):
                    sender_battle_before(task, None, 'config')
            normal.assert_not_called()
            path = next(Path(folder).glob('assist-*.json'))
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertFalse(data['accounts'][CooperationReport.account_key(task.support_account)]['verified'])

    def test_low_chapter_route_is_preferred_with_same_type_priority(self):
        from tasks.FindJade.WantedQuestsEx import sender_routes
        task = Mock()
        task.config.model.wanted_quests.wanted_quests_config = SimpleNamespace(
            battle_priority='探索 > 御魂', layer_limit=SimpleNamespace(value='柒'))
        task.sender_excluded_routes = set()
        for i, chapter in enumerate(['第二十七章','第七章','第二十三章','第九章'],1):
            getattr(task, 'O_WQ_TYPE_' + str(i)).ocr.return_value = '探索'
            getattr(task, 'O_WQ_INFO_' + str(i)).ocr.return_value = chapter + '(数量：2)'
        task.appear.return_value = True
        routes = sender_routes(task, None, 0)
        self.assertEqual([r[1] for r in routes], ['第七章','第九章','第二十三章','第二十七章'])

    def test_dynamic_enemy_object_click_uses_device_coordinates(self):
        from tasks.FindJade.WantedQuestsEx import sender_fire
        task = Mock()
        button = SimpleNamespace(coord=lambda: (1110,360))
        task.appear.return_value = True
        task.minions_cnt = 0
        task.run_general_battle.return_value = True
        with patch('tasks.FindJade.assist.prepare_exploration_assist_entry'):
            self.assertTrue(sender_fire(task, button))
        task.device.click.assert_called_once_with(1110,360,control_name='sender_enemy_start')
        task.click.assert_not_called()

    def test_verified_cache_does_not_skip_normal_battle_preparation(self):
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        task = Mock()
        with patch('tasks.FindJade.assist.ensure_sender_assist') as assist, \
                patch.object(GeneralBattle, 'battle_before', return_value=True) as normal:
            self.assertTrue(sender_battle_before(task, None, 'config'))
        assist.assert_called_once_with(task)
        normal.assert_called_once_with(task, None, 'config', timeout=45)


if __name__ == '__main__':
    unittest.main()
