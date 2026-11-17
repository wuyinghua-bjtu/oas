import asyncio
import json
from pathlib import Path
from urllib.request import urlopen

import websockets
import yaml


async def worker_state(port, name):
    async with websockets.connect(f'ws://127.0.0.1:{port}/ws/{name}', open_timeout=5) as connection:
        message = json.loads(await asyncio.wait_for(connection.recv(), 5))
        return message.get('state')


def verify_apprentice_idle(profile, owner):
    root = Path('config')
    settings = json.loads((root / f'{profile}.json').read_text(encoding='utf-8'))['script']['device']
    port = int(yaml.safe_load((root / 'deploy.yaml').read_text(encoding='utf-8'))['Deploy']['Webui']['WebuiPort'])
    try:
        with urlopen(f'http://127.0.0.1:{port}/config_list', timeout=5) as response:
            profiles = json.load(response)
        competing = {profile}
        for name in profiles:
            if name == owner or name == 'template':
                continue
            if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
                raise RuntimeError('配置列表包含无效名称')
            raw = json.loads((root / f'{name}.json').read_text(encoding='utf-8'))
            other = raw.get('script', {}).get('device', {})
            same_device = any(settings.get(key) and settings[key] == other.get(key)
                              for key in ('handle', 'serial', 'emulatorinfo_name'))
            paired_task = raw.get('running_task') in ('GroupedAwakening', 'TripleAwakening', 'Mentorship')
            if same_device or paired_task:
                competing.add(name)

        async def check():
            for name in sorted(competing):
                if await worker_state(port, name) != 0:
                    raise RuntimeError(f'{name} 仍在运行，不能接管徒弟模拟器')

        asyncio.run(check())
    except Exception as error:
        raise RuntimeError(f'无法确认徒弟模拟器空闲：{error}') from error
