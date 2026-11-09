"""Local, bounded failure handoff. No GUI actions, uploads or auto-repair."""
from collections import deque
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import time
import traceback
import uuid

from filelock import FileLock

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / 'log' / 'repair'
COOLDOWN_SECONDS = 1800


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def secrets_from_config(config_name, root=ROOT):
    """Read credentials only to remove them; never include raw config in reports."""
    secrets = []
    try:
        data = json.loads((Path(root) / 'config' / (config_name + '.json')).read_text(encoding='utf-8'))
        def walk(value, key=''):
            if isinstance(value, dict):
                for k, v in value.items():
                    walk(v, str(k))
            elif isinstance(value, list):
                for v in value:
                    walk(v, key)
            elif isinstance(value, str):
                if re.search(r'token|password|secret|api.?key|cookie|authorization', key, re.I):
                    if value:
                        secrets.append(value)
                if key == 'notify_config':
                    import yaml
                    for item in yaml.safe_load_all(value):
                        if isinstance(item, dict):
                            walk(item)
        walk(data)
    except Exception:
        pass
    return secrets


def redact(text, secrets=()):
    text = str(text)
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            text = text.replace(secret, '[REDACTED]')
    # Also covers rich tracebacks and one-line YAML/JSON representations.
    return re.sub(
        r"(?i)(\b(?:token|password|secret|api[_-]?key|cookie|authorization)\b[\"']?\s*[:=]\s*[\"']?)([^\s,;\"'\\}\]]+)",
        r'\1[REDACTED]', text)


def log_tail(path, max_bytes=192 * 1024):
    """Bound the read even when a daily log is hundreds of MB."""
    try:
        with Path(path).open('rb') as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read(max_bytes)
        if size > max_bytes:
            data = data.partition(b'\n')[2]
        return data.decode('utf-8', errors='replace')
    except (OSError, TypeError):
        return ''


def build_report(config_name, command, error, *, stage='', reason='recovery_exhausted',
                 attempts=0, recoveries=(), images=(), log_path=None, notifier=None,
                 root=REPORT_ROOT, secret_values=(), now=None):
    """Always save evidence; deduplicate only accepted notifications for 30 min.

    PNGs are LOCAL originals and may contain game nicknames. They are never sent
    to the notification provider. No config file or credential is copied.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    now = time.time() if now is None else now
    stamp = datetime.fromtimestamp(now).strftime('%Y%m%d_%H%M%S')
    safe_config = re.sub(r'[^\w.-]', '_', config_name)[:80]
    safe_command = re.sub(r'[^\w.-]', '_', command or 'Startup')[:80]
    folder = root / (stamp + '_' + safe_config + '_' + safe_command + '_' + uuid.uuid4().hex[:8])
    folder.mkdir()
    message = redact(str(error), secret_values)
    trace = redact(''.join(traceback.format_exception(type(error), error, error.__traceback__)), secret_values)
    normalized = re.sub(r'0x[0-9a-fA-F]+', '0xADDR', message)
    fingerprint = hashlib.sha256((config_name + '\n' + command + '\n' + type(error).__name__ + '\n' + normalized).encode()).hexdigest()
    manifest = {
        'schema_version': 1, 'created_at': datetime.fromtimestamp(now).isoformat(timespec='seconds'),
        'config': config_name, 'task': command or 'Startup', 'stage': redact(stage, secret_values),
        'reason': reason, 'error_type': type(error).__name__, 'error': message,
        'failed_invocations': attempts, 'recoveries': list(recoveries),
        'fingerprint': fingerprint, 'folder': str(folder.resolve()),
        'screenshots': [], 'evidence_errors': [],
        'notification': {'status': 'not_attempted'},
        'privacy': 'Logs redacted; original game screenshots stay local and may contain nicknames.',
        'repair_prompt': '处理最新错误' + ('（' + config_name + '）'),
    }
    (folder / 'traceback.txt').write_text(trace, encoding='utf-8')
    (folder / 'log_tail.txt').write_text(redact(log_tail(log_path), secret_values), encoding='utf-8')
    try:
        import cv2
        import numpy as np
        for i, image in enumerate(list(images)[-3:]):
            if not isinstance(image, np.ndarray) or image.size == 0:
                continue
            try:
                if image.ndim != 3 or image.shape[2] != 3:
                    raise ValueError('Expected RGB screenshot')
                ok, buffer = cv2.imencode('.png', cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
                if not ok:
                    raise ValueError('PNG encoding failed')
                name = 'failure_' + str(i + 1) + '.png'
                buffer.tofile(str(folder / name))
                manifest['screenshots'].append(name)
            except Exception as exc:
                manifest['evidence_errors'].append('Screenshot: ' + type(exc).__name__)
    except ImportError:
        manifest['evidence_errors'].append('Screenshot dependencies unavailable')
    manifest_path = folder / 'report.json'
    atomic_json(manifest_path, manifest)
    with FileLock(str(root / '.notification.lock'), timeout=10):
        state_path = root / 'notification_state.json'
        try:
            state = json.loads(state_path.read_text(encoding='utf-8'))
            if not isinstance(state, dict):
                state = {}
        except (OSError, ValueError):
            state = {}
        accepted_at = state.get(fingerprint)
        if isinstance(accepted_at, (float, int)) and 0 <= now - accepted_at < COOLDOWN_SECONDS:
            manifest['notification'] = {'status': 'deduplicated', 'cooldown_seconds': COOLDOWN_SECONDS}
        elif notifier is None:
            manifest['notification'] = {'status': 'unavailable'}
        else:
            content = ('配置：' + config_name + '\n任务：' + (command or 'Startup') +
                       '\n阶段：' + manifest['stage'] + '\n原因：' + type(error).__name__ + ': ' + message[:350] +
                       '\n失败次数：' + str(attempts) + '\n错误包：Backend/log/repair/' + folder.name +
                       '\n回到豆包说“处理最新错误（' + config_name + '）”。截图与日志已保存在本机，未上传。')
            try:
                accepted = notifier.push(title='OAS 需要修复：' + (command or 'Startup'), content=content)
                manifest['notification'] = {'status': 'request_accepted' if accepted else 'failed_or_disabled',
                                            'delivery_confirmed': False}
                if accepted:
                    state = {k: v for k, v in state.items() if isinstance(v, (float, int)) and now - v < 86400}
                    state[fingerprint] = now
                    atomic_json(state_path, state)
            except Exception as exc:
                manifest['notification'] = {'status': 'failed', 'error_type': type(exc).__name__}
        atomic_json(manifest_path, manifest)
        pointer = {'report': str(manifest_path.resolve()), 'config': config_name, 'task': command or 'Startup',
                   'created_at': manifest['created_at'], 'notification': manifest['notification']}
        atomic_json(root / ('latest_' + safe_config + '.json'), pointer)
        atomic_json(root / 'latest.json', pointer)
    return manifest


def report_script_failure(script, command, error, *, reason='recovery_exhausted'):
    """Best effort: do not instantiate a missing Device during failure handling."""
    from module.logger import logger
    values = vars(script)
    config_name = values.get('config_name', 'unknown')
    secret_values = secrets_from_config(config_name)
    config = values.get('config')
    notifier = None
    if config is not None:
        try:
            notifier = config.notifier
        except Exception:
            pass
    if notifier is None:
        try:
            from module.notify.notify import Notifier
            raw = json.loads((ROOT / 'config' / (config_name + '.json')).read_text(encoding='utf-8'))
            policy = raw.get('script', {}).get('error', {})
            notifier = Notifier(policy.get('notify_config', ''), enable=policy.get('notify_enable', False))
            notifier.config_name = config_name
        except Exception:
            pass
    images = list(values.get('_failure_images', {}).get(command, ()))
    device = values.get('device')
    if not images and device is not None:
        image = vars(device).get('image')
        if image is not None:
            images.append(image)
    failures = values.get('_task_failures', {}).get(command, {})
    try:
        result = build_report(config_name, command, error,
                              stage=failures.get('stage', values.get('_active_stage', command)),
                              reason=reason, attempts=failures.get('attempts', 1),
                              recoveries=failures.get('recoveries', []), images=images,
                              log_path=getattr(logger, 'log_file', None), notifier=notifier,
                              secret_values=secret_values)
        logger.warning('Local repair report saved: %s; notification=%s', result['folder'], result['notification']['status'])
        return result
    except Exception as exc:
        # Do not let diagnostics replace the original failure.
        try:
            logger.error('Repair report could not be saved: %s', type(exc).__name__)
        except Exception:
            pass
        return None
