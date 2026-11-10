import argparse
import ast
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def safe_defaults(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'enable' and isinstance(child, bool):
                value[key] = False
            elif key in ('account', 'account_alias', 'character', 'svr', 'password', 'token') and isinstance(child, str):
                value[key] = ''
            else:
                safe_defaults(child)
    elif isinstance(value, list):
        for child in value:
            safe_defaults(child)
    return value


def missing_templates():
    missing = set()
    for source in (ROOT / 'tasks').rglob('*.py'):
        tree = ast.parse(source.read_text(encoding='utf-8-sig'), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                filename = node.value.replace('\\', '/')
                filename = filename.removeprefix('./')
                if filename.startswith('tasks/') and filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    if not (ROOT / filename).is_file():
                        missing.add(filename)
    for source in (ROOT / 'tasks').rglob('image.json'):
        data = json.loads(source.read_text(encoding='utf-8-sig'))
        if not isinstance(data, list):
            continue
        for item in data:
            filename = item.get('imageName') if isinstance(item, dict) else None
            if filename and not (source.parent / filename).is_file():
                missing.add((source.parent / filename).relative_to(ROOT).as_posix())
    return sorted(missing)


def initialize(name):
    from module.config.config_model import ConfigModel

    folder = ROOT / 'config'
    folder.mkdir(exist_ok=True)
    defaults = safe_defaults(ConfigModel().model_dump(mode='json'))
    defaults['config_name'] = None
    for filename, data in [('template', defaults), (name, dict(defaults, config_name=name))]:
        destination = folder / f'{filename}.json'
        if destination.exists():
            print(f'KEEP {destination.name}')
            continue
        with destination.open('x', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        print(f'CREATED {destination.name}: tasks disabled; configure your own device')
    deploy = folder / 'deploy.yaml'
    if not deploy.exists():
        with deploy.open('x', encoding='utf-8') as handle:
            handle.write((ROOT / 'deploy' / 'template').read_text(encoding='utf-8'))
        print('CREATED deploy.yaml')


def main():
    parser = argparse.ArgumentParser(description='Initialize a private config without connecting to any device')
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--name', default='oas1')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', args.name) or args.name in ('template', 'deploy'):
        parser.error('Use a config name with letters, numbers, dash or underscore (not template/deploy)')
    if Path.cwd().resolve() != ROOT:
        parser.error('Run this command from the backend repository root')
    if args.init:
        initialize(args.name)
    missing = missing_templates()
    print(f'Missing explicitly referenced templates: {len(missing)}')
    for filename in missing:
        print(f'  {filename}')
    print('Affected features require locally recreated templates. No emulator or game was accessed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
