import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tasks.FindJade.report import CooperationReport


class SenderCompletedReconcileTests(unittest.TestCase):
    def report(self):
        report = CooperationReport.__new__(CooperationReport)
        report.flush = Mock()
        report.records = {'quest': {'character': 'test4', 'server': 'server',
                                   'category': '勾协', 'reward': '勾玉',
                                   'invitations': [{'sender_work_required': True, 'sender_completed': False}]}}
        return report

    def test_unique_matching_completed_card_reconciles(self):
        report = self.report()
        account = SimpleNamespace(character='test4', svr='server')
        self.assertTrue(report.reconcile_completed_sender(account, [
            {'type': 2, 'already_shared': True, 'completed': True}]))
        self.assertEqual(report.sender_pending(account), [])
        report.flush.assert_called_once()

    def test_assist_deferral_is_restored_without_completing_work(self):
        report = self.report()
        account = SimpleNamespace(character='test4', svr='server')
        event = report.records['quest']['invitations'][0]
        event.update(sender_deferred=True, sender_deferred_reason='首次好友协战未上阵确认：未识别')
        self.assertTrue(report.restore_assist_deferred(account))
        self.assertNotIn('sender_deferred', event)
        self.assertFalse(event['sender_completed'])
        self.assertEqual(len(report.sender_pending(account)), 1)

    def test_real_defeat_remains_deferred(self):
        report = self.report()
        account = SimpleNamespace(character='test4', svr='server')
        event = report.records['quest']['invitations'][0]
        event.update(sender_deferred=True, sender_deferred_reason='小号协作战斗失败')
        self.assertFalse(report.restore_assist_deferred(account))
        self.assertTrue(event['sender_deferred'])
        report.flush.assert_not_called()

    def test_unfinished_mismatched_or_duplicate_card_does_not_reconcile(self):
        account = SimpleNamespace(character='test4', svr='server')
        for cards in ([{'type': 2, 'already_shared': True, 'completed': False}],
                      [{'type': 4, 'reward_kind': 'DOG_FOOD', 'already_shared': True, 'completed': True}],
                      [{'type': 2, 'already_shared': True, 'completed': True}] * 2):
            report = self.report()
            self.assertFalse(report.reconcile_completed_sender(account, cards))
            self.assertEqual(len(report.sender_pending(account)), 1)
            report.flush.assert_not_called()


if __name__ == '__main__':
    unittest.main()
