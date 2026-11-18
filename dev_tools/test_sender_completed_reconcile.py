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
