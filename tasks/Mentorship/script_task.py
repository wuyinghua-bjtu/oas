"""Daily two-device mentorship task for OAS1."""
from module.config.local_values import local_text
import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import psutil
from module.config.config import Config
from module.device.app_control import AppControl
from module.exception import (ScriptEnd, TaskEnd, GameSessionExpiredError,
                             GameNotRunningError, GameStuckError)
from module.logger import logger
from tasks.base_task import BaseTask
from tasks.TripleAwakening.device import TeamDevice
from tasks.TripleAwakening.script_task import MANAGER, Participant
from tasks.GroupedAwakening.session_guard import install_login_expiry_guard
from tasks.FindJade.script_task import ScriptTask as FindJade
from tasks.Mentorship.daily_device import run_verified_daily
from tasks.Mentorship.apprentice_souls import NoAssistShikigami
from tasks.Mentorship.navigation import leave_activity_menu
from tasks.Mentorship.vision import detect
from tasks.GameUi.page import page_login
from tasks.Mentorship.battle_pair import clear_verified_statistics


class ScriptTask(BaseTask):
    def run(self):
        if self.config.config_name != 'oas1':
            raise ScriptEnd('师徒任务只支持 oas1')
        directory = Path('log/mentorship/oas1')
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (datetime.now().strftime('%Y-%m-%d') + '.json')
        state = {'status': '运行中', 'updated_at': datetime.now().isoformat(timespec='seconds')}
        def save():
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(path)
        save()
        guarded = []
        try:
            options = self.config.model.mentorship.mentorship_config
            apprentice_name = options.apprentice_name.strip()
            apprentice_server = options.apprentice_server.strip()
            if not apprentice_name or not apprentice_server:
                raise RuntimeError('请填写徒弟角色名和服务器')
            state.update(apprentice=apprentice_name, server=apprentice_server)
            save()
            other_path = Path('config/oas_leveling.json')
            raw = json.loads(other_path.read_text(encoding='utf-8'))
            if raw.get('running_task') in ('GroupedAwakening', 'TripleAwakening', 'Mentorship'):
                raise RuntimeError('其他任务可能正在使用徒弟模拟器')
            inventory = json.loads(subprocess.check_output(
                [str(MANAGER), 'info', '-v', 'all'], creationflags=subprocess.CREATE_NO_WINDOW))
            configs, devices = [], []
            for profile in ('oas1', 'oas_leveling'):
                config = Config(profile)
                settings = config.model.script.device
                # Resolve the emulator from the profile's own handle. Hard-coding
                # the name once picked a clone instance that held the same
                # apprentice account, so the two clients kicked each other off.
                title = settings.handle
                matches = [item for item in inventory.values()
                           if item.get('name') == title and item.get('is_android_started')]
                if len(matches) != 1:
                    raise RuntimeError(title + ' 未开机或窗口不唯一')
                info = matches[0]
                settings.handle = title
                settings.serial = f"{info['adb_host_ip']}:{info['adb_port']}"
                args = psutil.Process(info['pid']).cmdline()
                settings.emulatorinfo_name = args[args.index('--vm') + 1]
                settings.screenshot_method, settings.control_method = 'window_background', 'window_message'
                settings.adb_restart = settings.emulator_window_minimize = False
                device = TeamDevice(config, info)
                guarded.append((device, install_login_expiry_guard(device, title)))
                configs.append(config)
                devices.append(device)
            accounts = [a for a in configs[1].find_jade.sup_account_list
                        if a.character == apprentice_name and a.svr == apprentice_server and a.is_valid()
                        and a.account and a.apple_or_android]
            if len(accounts) != 1:
                raise RuntimeError(f'{apprentice_server} 的 {apprentice_name} 必须在小号列表中有唯一有效的安卓账号')
            for device in devices:
                clear_verified_statistics(device, apprentice_name)
            for index, expected in enumerate((local_text('LOCAL_SUPPORT_'), apprentice_name)):
                player = Participant(configs[index], devices[index])
                player.step('师徒角色核对', 120)
                devices[index].stuck_record_clear()
                devices[index].click_record_clear()
                devices[index].screenshot()
                if detect(devices[index].image, 'guard_entry') and not leave_activity_menu(devices[index]):
                    raise RuntimeError('无法离开妖气探索')
                actual = self.read_identity(player, devices[index])
                if index == 1 and actual != expected:
                    player.step('切换指定徒弟', 300)
                    switched = False
                    for attempt in range(2):
                        try:
                            switched = FindJade.switch_support_account(player, accounts[0])
                            break
                        except GameNotRunningError as error:
                            # The client can drop to the login page while the
                            # switch is navigating; the retry starts right on
                            # page_login and logs the account in there.
                            logger.warning(f'{expected}: 切号被登录页打断（{error}），切号重试 {attempt + 1}')
                            player.step('切换指定徒弟重试', 300)
                            player.ui_get_current_page()
                    if not switched:
                        raise RuntimeError('无法切换指定徒弟')
                    player.step('切号后核对徒弟', 150)
                    actual = self.read_identity(player, devices[index], recover_game=False)
                if actual != expected:
                    devices[index].save_screenshot(genre='mentorship_identity_unrecognized', interval=0)
                    raise RuntimeError(f'角色不符：预期 {expected}，实际 {actual}')
            run_verified_daily(configs[0], devices[0], devices[1], apprentice_name,
                               apprentice_config=configs[1], apprentice_server=apprentice_server)
            state.update(status='完成', updated_at=datetime.now().isoformat(timespec='seconds'))
            save()
        except NoAssistShikigami as error:
            state.update(status='已跳过', reason=str(error), updated_at=datetime.now().isoformat(timespec='seconds'))
            save()
            try:
                self.config.notifier.push(title='师徒任务已跳过',
                                          content=f'徒弟：{apprentice_name}\n原因：{error}\n将继续执行后续任务。')
            except Exception:
                logger.exception('师徒缺少协战通知发送失败')
        except Exception as error:
            state.update(status='出错', reason=str(error) or type(error).__name__, updated_at=datetime.now().isoformat(timespec='seconds'))
            save()
            logger.exception(error)
            raise ScriptEnd('师徒任务停止：' + str(error)) from error
        finally:
            for device, original in guarded:
                device.screenshot = original
        now = datetime.now()
        target = (now + timedelta(days=1)).replace(hour=0, minute=30, second=0, microsecond=0)
        self.set_next_run('Mentorship', server=False, finish=True, target=target)
        raise TaskEnd('Mentorship')

    def read_identity(self, player, device, recover_game=True, wait=120):
        """Read the courtyard nickname, recovering a closed client or login page.

        The emulator itself is never stopped: a closed client is only relaunched,
        and a client sitting on the login page is reported as unknown so the
        caller can switch to the configured account.
        """
        name = device.config.script.device.handle
        for attempt in range(2):
            if not device.app_is_running():
                if not recover_game or attempt:
                    logger.warning(f'{name}: 游戏未运行，无法核对角色')
                    return None
                logger.warning(f'{name}: 游戏未在前台，重新启动游戏')
                # TeamDevice forbids app_start as a team-task guard, but the
                # mentorship flow has to relaunch only the game client; the
                # emulator itself is never stopped.
                AppControl.app_start(device)
                deadline = time.monotonic() + wait
                while time.monotonic() < deadline:
                    time.sleep(2)
                    try:
                        device.screenshot()
                    except GameStuckError:
                        pass
                    if device.app_is_running():
                        break
                else:
                    logger.warning(f'{name}: 启动游戏后仍未进入前台')
                    return None
                time.sleep(3)
            try:
                if player.ui_page_appear(page_login):
                    logger.warning(f'{name}: 游戏停在登录页，交给切号处理')
                    return None
                return player.nickname()
            except GameNotRunningError as error:
                logger.warning(f'{name}: 读取角色名失败（游戏未运行）：{error}')
                recover_game = True
                continue
            except GameStuckError as error:
                logger.warning(f'{name}: 读取角色名失败：{error}')
                return None
        return None
