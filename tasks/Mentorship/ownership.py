import asyncio
import json
import time
from pathlib import Path
from urllib.request import urlopen

import websockets
import yaml


async def worker_state(port, name):
    async with websockets.connect(f'ws://127.0.0.1:{port}/ws/{name}', open_timeout=5) as connection:
        message = json.loads(await asyncio.wait_for(connection.recv(), 5))
        return message.get('state')


def _worker_action(port, profile, action):
    with urlopen(f'http://127.0.0.1:{port}/{profile}/{action}', timeout=10) as response:
        response.read()


def resume_apprentice(profile):
    port = int(yaml.safe_load(Path('config/deploy.yaml').read_text(encoding='utf-8'))
               ['Deploy']['Webui']['WebuiPort'])
    _worker_action(port, profile, 'start')


def acquire_apprentice(profile, owner):
    port = int(yaml.safe_load(Path('config/deploy.yaml').read_text(encoding='utf-8'))
               ['Deploy']['Webui']['WebuiPort'])
    state = asyncio.run(worker_state(port, profile))
    if state == 0:
        verify_apprentice_idle(profile, owner)
        return False
    if state != 1:
        raise RuntimeError('徒弟脚本状态异常，不能接管')
    for attempt in range(2):
        raw = json.loads((Path('config') / f'{profile}.json').read_text(encoding='utf-8'))
        if raw.get('running_task') != '':
            raise RuntimeError('徒弟正在执行任务，不能接管')
        if attempt == 0:
            time.sleep(1)
    paused = False
    try:
        _worker_action(port, profile, 'stop')
        paused = True
        for attempt in range(10):
            if asyncio.run(worker_state(port, profile)) == 0:
                verify_apprentice_idle(profile, owner)
                return True
            time.sleep(.5)
        raise RuntimeError('徒弟空闲监听未确认暂停')
    except Exception:
        if paused:
            resume_apprentice(profile)
        raise


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
