"""Atomic ledger writes and exact, already-settled round recovery."""
import json
import os
import tempfile
import time
from pathlib import Path


def atomic_json_write(path, record, attempts=20):
    path = Path(path)
    payload = json.dumps(record, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                     dir=path.parent, prefix=path.stem + '_',
                                     suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        for attempt in range(attempts):
            try:
                temporary.replace(path)
                return
            except PermissionError as error:
                if getattr(error, 'winerror', None) not in (None, 5, 32, 33) or attempt + 1 == attempts:
                    raise
                time.sleep(0.1)
    finally:
        # Only our unique temporary file; never delete the ledger on failure.
        try:
            temporary.unlink(missing_ok=True)
        except PermissionError:
            pass


def finalize_settled_round(entry, windows, finished_at):
    """Credit once only when durable evidence confirms every win and settlement."""
    pending = entry.get('pending_round', {})
    expected_round = entry['completed'] + 1
    if (not entry.get('battle_in_progress') or entry.get('battle_phase') != 'fighting'
            or entry.get('active_round') != expected_round
            or pending.get('round') != expected_round
            or expected_round > entry['target']):
        return False
    for field in ('won', 'settled'):
        evidence = pending.get(field, {})
        if set(evidence) != set(windows) or not all(evidence[w] is True for w in windows):
            return False
    entry['completed'] = expected_round
    entry['rounds'].append({'round': expected_round, 'all_won': True,
                            'recovered': True, 'finished_at': finished_at,
                            'evidence': 'durable_all_won_and_settled'})
    for field in ('pending_round', 'battle_in_progress', 'active_round', 'battle_phase'):
        entry.pop(field, None)
    return True
