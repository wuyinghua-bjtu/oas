"""Run the explicitly bound mentorship workflow under emulator safeguards."""
import json
from module.config.local_values import local_text
import subprocess
import psutil
from module.config.config import Config
from tasks.TripleAwakening.device import TeamDevice
from tasks.TripleAwakening.script_task import MANAGER, Participant
from tasks.GroupedAwakening.session_guard import install_login_expiry_guard
from tasks.Mentorship.daily_device import run_verified_daily
from tasks.Mentorship.vision import detect
from tasks.Mentorship.navigation import leave_activity_menu

inventory = json.loads(subprocess.check_output([str(MANAGER), 'info', '-v', 'all']))
configs, devices = [], []
for profile, title in [('oas1', 'MuMu安卓设备'), ('oas_leveling', 'MuMu安卓设备-1-1')]:
    config = Config(profile)
    info = next(x for x in inventory.values() if x['name'] == title and x['is_android_started'])
    settings = config.model.script.device
    settings.handle = title
    settings.serial = f"{info['adb_host_ip']}:{info['adb_port']}"
    args = psutil.Process(info['pid']).cmdline()
    settings.emulatorinfo_name = args[args.index('--vm') + 1]
    settings.screenshot_method, settings.control_method = 'window_background', 'window_message'
    settings.adb_restart = settings.emulator_window_minimize = False
    device = TeamDevice(config, info)
    install_login_expiry_guard(device, title)
    configs.append(config)
    devices.append(device)

participant = Participant(configs[1], devices[1])
devices[1].screenshot()
if detect(devices[1].image, 'guard_entry') and not leave_activity_menu(devices[1]):
    raise RuntimeError('无法退出徒弟妖气探索页面')
participant.step('确认徒弟身份', 90)
if participant.nickname() != local_text('LOCAL_SUPPORT_004'):
    raise RuntimeError('徒弟角色不匹配')
leader = Participant(configs[0], devices[0])
devices[0].screenshot()
if detect(devices[0].image, 'guard_entry') and not leave_activity_menu(devices[0]):
    raise RuntimeError('无法退出师父妖气探索页面')
leader.step('确认师父身份', 90)
if leader.nickname() != local_text('LOCAL_SUPPORT_'):
    raise RuntimeError('师父角色不匹配')
run_verified_daily(configs[0], devices[0], devices[1], local_text('LOCAL_SUPPORT_004'), apprentice_config=configs[1])
