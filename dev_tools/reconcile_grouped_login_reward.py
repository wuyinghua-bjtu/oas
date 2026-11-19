import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from module.atom.ocr import RuleOcr
from tasks.GroupedAwakening.ledger import atomic_json_write


def reconcile(ledger_path, screenshot_path, group_number):
    record = json.loads(ledger_path.read_text(encoding='utf-8'))
    entry = record['groups'][group_number - 1]
    pending = entry['pending_round']
    windows = list(entry['bindings'])
    leader = windows[0]
    captured_at = datetime.fromtimestamp(int(screenshot_path.stem) / 1000)
    if not datetime.fromisoformat(entry['battle_started_at']) <= captured_at <= datetime.fromisoformat(record['updated_at']):
        raise RuntimeError('Screenshot timestamp does not belong to this interrupted round')
    if (not entry.get('battle_in_progress') or entry.get('battle_phase') != 'fighting'
            or pending['round'] != entry['completed'] + 1
            or entry['active_round'] != pending['round']
            or not all(pending['won'].get(window) is True for window in windows[1:])):
        raise RuntimeError('Round or teammate victory evidence is incomplete')
    image = np.array(Image.open(screenshot_path).convert('RGB'))
    box = (350, 590, 600, 110)
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default', keyword='', name='login_reward_receipt')
    labels = ''.join(row.ocr_text for row in reader.detect_and_ocr(image)).replace(' ', '')
    if not all(label in labels for label in ('额外加成', '好友', '组队', '屏幕继续')):
        raise RuntimeError('Screenshot does not confirm the team reward screen')
    backup = ledger_path.with_name(ledger_path.stem + '_before_login_reward_' + datetime.now().strftime('%H%M%S') + '.json')
    backup.write_bytes(ledger_path.read_bytes())
    pending['won'][leader] = True
    entry['login_reward_evidence'] = {'round': pending['round'], 'screenshot': str(screenshot_path),
                                    'labels': labels, 'recorded_at': datetime.now().isoformat(timespec='seconds')}
    atomic_json_write(ledger_path, record)
    print('Reward evidence recorded; completed count remains', entry['completed'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('ledger', type=Path)
    parser.add_argument('screenshot', type=Path)
    parser.add_argument('group', type=int)
    args = parser.parse_args()
    reconcile(args.ledger, args.screenshot, args.group)
