"""Migrate EyeAwakening accounts into its own editable groups, without changing other tasks."""
import json
import shutil
from datetime import datetime
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = root / 'work' / 'eye_accounts_backup' / stamp
    paths = [root / 'config' / (name + '.json') for name in
             ('oas_eye_1', 'oas_eye_2', 'oas_eye_3', 'oas_leveling', 'template')]
    translations = root / 'assets' / 'i18n' / 'zh-CN.json'
    additions = {
        'eye_account_1': '第1个小号（先执行）',
        'eye_account_2': '第2个小号',
        'eye_account_3': '第3个小号',
        'eye_account_4': '第4个小号（最后执行）',
        'max_battles_per_account': '每个小号战斗次数上限',
    }
    for path in paths:
        data = json.loads(path.read_text(encoding='utf8'))
        eye = data.setdefault('eye_awakening', {})
        if all(f'eye_account_{i}' in eye for i in range(1, 5)):
            continue
        selection = data.get('guild_quick_participation', {}).get('guild_accounts', {})
        names = [s.strip() for s in selection.get('characters', '').replace('，', ',').replace(',', '\n').splitlines() if s.strip()]
        pool = [v for k, v in data.get('find_jade', {}).items() if k.startswith('sup_account_list_')]
        selected = []
        if path.stem != 'template':
            for name in names[:4]:
                matches = [v for v in pool if v.get('character') == name and v.get('svr') == selection.get('server')]
                if len(matches) != 1:
                    raise ValueError(f'{path.stem}: cannot uniquely migrate character')
                selected.append(matches[0])
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup / path.name)
        for i in range(1, 5):
            eye.setdefault(f'eye_account_{i}', selected[i-1].copy() if i <= len(selected) else {
                'character': '', 'svr': '', 'account': '', 'account_alias': '',
                'apple_or_android': True, 'last_complete_time': '2023-01-01 00:00:00'})
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        print('migrated', path.stem)
    data = json.loads(translations.read_text(encoding='utf8'))
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(translations, backup / 'translations.json')
    data.update(additions)
    translations.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('backup:', backup)


if __name__ == '__main__':
    main()
