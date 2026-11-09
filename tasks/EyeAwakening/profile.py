"""Fixed, isolated profiles for the three single-account farming workers."""
import asyncio
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen

import websockets
import yaml

from module.exception import RequestHumanTakeover


PROFILES = {
    'oas_eye_1': {'window': 'MuMu安卓设备-1', 'serial': '127.0.0.1:16416', 'vm': 'MuMuPlayer-15.0-1', 'index': '1',
                  'characters': ('OASPlayer001', 'OASPlayer002', 'OASPlayer003', 'OASPlayer004')},
    'oas_eye_2': {'window': 'MuMu安卓设备-1-1', 'serial': '127.0.0.1:16448', 'vm': 'MuMuPlayer-15.0-2', 'index': '2',
                  'characters': ('OASPlayer005', 'OASPlayer006', 'OASPlayer007', 'OASPlayer008')},
    'oas_eye_3': {'window': 'MuMu安卓设备-1-2', 'serial': '127.0.0.1:16480', 'vm': 'MuMuPlayer-15.0-3', 'index': '3',
                  'characters': ('OASPlayer009', 'OASPlayer010', 'OASPlayer011', 'OASMain2')},
}
MANAGER = Path('C:/Program Files/Netease/MuMu/nx_main/MuMuManager.exe')


def validate_profile(config):
    spec = PROFILES[config.config_name]
    device = config.model.script.device
    if (device.handle, device.serial, device.emulatorinfo_name) != (spec['window'], spec['serial'], spec['vm']):
        raise RequestHumanTakeover('配置与指定模拟器绑定不符，停止启动')
    names = [s.strip() for s in str(config.model.guild_quick_participation.guild_accounts.characters)
             .replace('，', ',').replace(',', '\n').splitlines() if s.strip()]
    if tuple(names) != spec['characters']:
        raise RequestHumanTakeover('小号分组名单已变化，停止启动以免重复刷号')
    try:
        inventory = json.loads(subprocess.check_output(
            [str(MANAGER), 'info', '-v', 'all'], timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)))
        found = [info for info in inventory.values() if info.get('name') == spec['window']]
        if len(found) != 1 or not found[0].get('is_android_started'):
            raise RequestHumanTakeover(f"{spec['window']} 未启动或名称重复，请先手动确认模拟器")
        if str(found[0].get('index')) != spec['index']:
            raise RequestHumanTakeover(f"{spec['window']} 的模拟器编号与配置不一致")
        actual = f"{found[0].get('adb_host_ip')}:{found[0].get('adb_port')}"
        if actual != spec['serial']:
            raise RequestHumanTakeover(f"{spec['window']} 的 ADB 端口与配置不一致")
        port = int(yaml.safe_load(Path('config/deploy.yaml').read_text(encoding='utf8'))['Deploy']['Webui']['WebuiPort'])
        with urlopen(f'http://127.0.0.1:{port}/config_list', timeout=5) as response:
            profiles = json.load(response)
        competing = []
        for name in profiles:
            if name == config.config_name:
                continue
            path = Path('config') / (name + '.json')
            raw = json.loads(path.read_text(encoding='utf8'))
            other = raw.get('script', {}).get('device', {})
            if other.get('handle') == spec['window'] or other.get('serial') == spec['serial']:
                competing.append(name)

        async def check_states():
            for name in competing:
                async with websockets.connect(f'ws://127.0.0.1:{port}/ws/{name}', open_timeout=5) as ws:
                    message = json.loads(await asyncio.wait_for(ws.recv(), 5))
                    if message.get('state') != 0:
                        raise RequestHumanTakeover(f'{name} 正在使用相同模拟器，请先停止该配置')
        asyncio.run(check_states())
    except RequestHumanTakeover:
        raise
    except Exception as error:
        raise RequestHumanTakeover(f'无法核实设备或其他 OAS 配置状态，停止启动：{type(error).__name__}') from error
