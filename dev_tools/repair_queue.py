"""Persistent, single-flight queue for Doubao local repair tasks.

No model API, emulator actions, shell execution or source writes. Candidate
patches are produced by the scheduled assistant, never applied by this module.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
import uuid

from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


class RepairQueue:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.reports = self.root / 'log' / 'repair'
        self.directory = self.root / 'work' / 'auto_repair'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'queue.json'
        self.lock = FileLock(str(self.path) + '.lock', timeout=10)

    def read(self):
        if not self.path.exists():
            return {'version': 1, 'jobs': {}}
        state = json.loads(self.path.read_text(encoding='utf-8'))
        if state.get('version') != 1 or not isinstance(state.get('jobs'), dict):
            raise ValueError('Invalid queue; preserve it and request manual review')
        return state

    def scan(self):
        with self.lock:
            state = self.read()
            for path in sorted(self.reports.glob('*/report.json')):
                resolved = path.resolve()
                if not resolved.is_relative_to(self.reports.resolve()):
                    continue
                try:
                    report = json.loads(path.read_text(encoding='utf-8'))
                    if report.get('config') not in ('oas1', 'oas_leveling'):
                        continue
                    fingerprint = report.get('fingerprint')
                    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
                        continue
                    # Dedup throughout the whole queue lifecycle, not just push cooldown.
                    if fingerprint in state['jobs']:
                        state['jobs'][fingerprint]['latest_report'] = str(resolved)
                        continue
                    state['jobs'][fingerprint] = {
                        'status': 'pending', 'report': str(resolved), 'latest_report': str(resolved),
                        'config': report['config'], 'task': report.get('task', ''),
                        'created_at': report.get('created_at', ''), 'attempts': 0,
                    }
                except (OSError, ValueError, TypeError):
                    continue
            write_json(self.path, state)
            return state

    def claim(self, now=None):
        self.scan()
        now = time.time() if now is None else now
        with self.lock:
            state = self.read()
            # Never retry stale work automatically: a previous source change or
            # test may still be running. Require manual review after 45 minutes.
            for job in state['jobs'].values():
                if job['status'] == 'running':
                    if now - job['claimed_at'] > 2700:
                        job['status'] = 'blocked'
                        job['reason'] = 'Lease expired; outcome unknown, no automatic replay'
                    else:
                        write_json(self.path, state)
                        return {'status': 'busy'}
            pending = [(key, job) for key, job in state['jobs'].items() if job['status'] == 'pending']
            if not pending:
                write_json(self.path, state)
                return {'status': 'empty'}
            key, job = min(pending, key=lambda pair: pair[1]['created_at'])
            owner = uuid.uuid4().hex
            workspace = self.directory / ('candidate_' + key[:16])
            workspace.mkdir(exist_ok=True)
            job.update(status='running', claimed_at=now, owner=owner, attempts=1, workspace=str(workspace))
            report = json.loads(Path(job['report']).read_text(encoding='utf-8'))
            request = {
                'config': job['config'], 'task': job['task'], 'report': job['report'],
                'fingerprint': key, 'owner': owner, 'workspace': str(workspace),
                'policy': str(self.directory / 'POLICY.md'),
                'error_type': report.get('error_type', ''),
                'mode': 'diagnose_candidate_and_offline_test_only',
            }
            write_json(workspace / 'request.json', request)
            write_json(self.path, state)
            return {'status': 'claimed', **request}

    def finish(self, fingerprint, owner, status, summary):
        if status not in ('candidate_ready', 'blocked', 'failed', 'already_fixed'):
            raise ValueError('Unsupported final status')
        with self.lock:
            state = self.read()
            job = state['jobs'][fingerprint]
            if job['status'] != 'running' or job.get('owner') != owner:
                raise ValueError('Claim ownership mismatch; do not overwrite outcome')
            if status == 'candidate_ready':
                workspace = Path(job['workspace'])
                for name in ('candidate.patch', 'diagnosis.md', 'test_results.txt', 'base_hashes.json', 'validation.json'):
                    if not (workspace / name).is_file():
                        raise ValueError('Candidate evidence missing: ' + name)
                validation = json.loads((workspace / 'validation.json').read_text(encoding='utf-8'))
                if validation.get('offline_tests_passed') is not True or validation.get('tests_executed', 0) < 1:
                    raise ValueError('Recorded offline tests did not pass')
            job.update(status=status, summary=str(summary)[:2000], finished_at=datetime.now().isoformat(timespec='seconds'))
            write_json(Path(job['workspace']) / 'result.json', {k: v for k, v in job.items() if k != 'owner'})
            write_json(self.path, state)
            return {'status': status, 'workspace': job['workspace']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['scan', 'claim', 'finish', 'status'])
    parser.add_argument('--fingerprint')
    parser.add_argument('--owner')
    parser.add_argument('--status')
    parser.add_argument('--summary', default='')
    args = parser.parse_args()
    queue = RepairQueue()
    if args.action == 'claim':
        result = queue.claim()
    elif args.action == 'finish':
        result = queue.finish(args.fingerprint, args.owner, args.status, args.summary)
    elif args.action == 'scan':
        result = queue.scan()
    else:
        with queue.lock:
            result = queue.read()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
