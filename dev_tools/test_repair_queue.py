import json
from pathlib import Path
import tempfile
import unittest
from dev_tools.repair_queue import RepairQueue


class RepairQueueTests(unittest.TestCase):
    def report(self, root, name, fingerprint='a' * 64):
        folder = Path(root) / 'log' / 'repair' / name
        folder.mkdir(parents=True)
        (folder / 'report.json').write_text(json.dumps({'config': 'oas1', 'task': 'RealmRaid',
            'fingerprint': fingerprint, 'created_at': name}), encoding='utf-8')

    def test_dedup_single_flight_and_finish(self):
        with tempfile.TemporaryDirectory() as root:
            self.report(root, '001')
            self.report(root, '002')
            queue = RepairQueue(root)
            self.assertEqual(len(queue.scan()['jobs']), 1)
            claim = queue.claim(now=100)
            self.assertEqual(claim['status'], 'claimed')
            self.assertEqual(queue.claim(now=101)['status'], 'busy')
            with self.assertRaises(ValueError):
                queue.finish(claim['fingerprint'], 'wrong', 'failed', '')
            with self.assertRaises(ValueError):
                queue.finish(claim['fingerprint'], claim['owner'], 'candidate_ready', '')
            workspace = Path(claim['workspace'])
            (workspace / 'candidate.patch').write_text('test patch', encoding='utf-8')
            for name in ('diagnosis.md', 'test_results.txt', 'base_hashes.json'):
                (workspace / name).write_text('{}', encoding='utf-8')
            (workspace / 'validation.json').write_text(json.dumps({'offline_tests_passed': True, 'tests_executed': 1}), encoding='utf-8')
            queue.finish(claim['fingerprint'], claim['owner'], 'candidate_ready', 'offline tests passed')
            self.report(root, '003')
            self.assertEqual(queue.claim(now=102)['status'], 'empty')

    def test_expired_lease_not_replayed(self):
        with tempfile.TemporaryDirectory() as root:
            self.report(root, '001')
            queue = RepairQueue(root)
            queue.claim(now=100)
            self.assertEqual(queue.claim(now=3000)['status'], 'empty')
            self.assertEqual(queue.read()['jobs']['a' * 64]['status'], 'blocked')

    def test_corrupted_state_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            queue = RepairQueue(root)
            queue.path.write_text('invalid', encoding='utf-8')
            with self.assertRaises(ValueError):
                queue.scan()
            self.assertEqual(queue.path.read_text(encoding='utf-8'), 'invalid')


if __name__ == '__main__':
    unittest.main()
