"""Offline ledger tests: no devices, windows or game actions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tasks.GroupedAwakening.ledger import atomic_json_write, finalize_settled_round


class LedgerTests(unittest.TestCase):
    def entry(self):
        return {'completed': 0, 'target': 15, 'rounds': [],
                'battle_in_progress': True, 'battle_phase': 'fighting', 'active_round': 1,
                'pending_round': {'round': 1, 'won': {'a': True, 'b': True},
                                  'settled': {'a': True, 'b': True}}}

    def test_finalize_once(self):
        entry = self.entry()
        self.assertTrue(finalize_settled_round(entry, ['a', 'b'], 'now'))
        self.assertFalse(finalize_settled_round(entry, ['a', 'b'], 'later'))
        self.assertEqual(entry['completed'], 1)
        self.assertEqual(len(entry['rounds']), 1)

    def test_missing_or_wrong_evidence_never_credits(self):
        for field in ['won', 'settled']:
            entry = self.entry()
            entry['pending_round'][field]['b'] = False
            before = copy.deepcopy(entry)
            self.assertFalse(finalize_settled_round(entry, ['a', 'b'], 'now'))
            self.assertEqual(entry, before)
        entry = self.entry()
        entry['pending_round']['round'] = 2
        self.assertFalse(finalize_settled_round(entry, ['a', 'b'], 'now'))
        self.assertFalse(finalize_settled_round(self.entry(), ['a', 'c'], 'now'))

    def test_atomic_write_retries_transient_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ledger.json'
            path.write_text('{"old": true}', encoding='utf-8')
            original = Path.replace
            calls = []
            def replace(source, target):
                calls.append(source)
                if len(calls) < 3:
                    raise PermissionError('temporary sharing violation')
                return original(source, target)
            with patch.object(Path, 'replace', replace), patch('tasks.GroupedAwakening.ledger.time.sleep'):
                atomic_json_write(path, {'角色': '测试'})
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'角色': '测试'})
            self.assertEqual(len(calls), 3)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_persistent_lock_preserves_original_and_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ledger.json'
            path.write_text('{"old": true}', encoding='utf-8')
            with patch.object(Path, 'replace', side_effect=PermissionError('locked')) as replace, \
                    patch('tasks.GroupedAwakening.ledger.time.sleep'):
                with self.assertRaises(PermissionError):
                    atomic_json_write(path, {'new': True}, attempts=3)
            self.assertEqual(replace.call_count, 3)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'old': True})
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
