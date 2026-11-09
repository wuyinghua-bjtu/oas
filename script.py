# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

from functools import wraps
import zerorpc
import zmq
import msgpack
import random
import re
import cv2
import time
import os
import inflection
import asyncio
import json

from datetime import date
import threading
from typing import Callable
from datetime import datetime, timedelta
from pathlib import Path
from cached_property import cached_property
from pydantic import BaseModel, ValidationError
from threading import Thread
from multiprocessing.queues import Queue


from module.config.utils import convert_to_underscore
from module.config.config import Config
from module.config.config_model import ConfigModel
from module.config.instance_guard import InstanceGuard
from module.device.device import Device
from module.device.env import IS_WINDOWS
from module.base.utils import load_module
from module.base.decorator import del_cached_property
from module.logger import logger
from module.exception import *
from module.server.i18n import I18n
from module.ocr.rpc import ensure_ocr_server_started



_log_switch_lock = threading.Lock()#线程锁


class Script:
    def __init__(self, config_name: str ='oas') -> None:
        logger.hr('Start', level=0)
        self.server = None
        self.state_queue: Queue = None
        self._emulator_down = False
        self.gui_update_task: Callable = None  # 回调函数, gui进程注册当每次config更新任务的时候更新gui的信息
        self.config_name = config_name
        # Skip first restart
        self.is_first_task = True
        # Failure count of tasks
        # Key: str, task name, value: int, failure count
        self.failure_record = {}
        # 运行loop的线程
        self.loop_thread: Thread = None
        # 跨进程排队管理器（仅在 queue_mode=True 时初始化）
        self.instance_guard: InstanceGuard = None

    @cached_property
    def config(self) -> "Config":
        try:
            from module.config.config import Config
            config = Config(config_name=self.config_name)
            return config
        except RequestHumanTakeover:
            logger.critical('Request human takeover')
            exit(1)
        except Exception as e:
            logger.exception(e)
            exit(1)

    @cached_property
    def device(self) -> "Device":
        try:
            from tasks.EyeAwakening.profile import PROFILES, validate_profile
            if self.config_name in PROFILES:
                validate_profile(self.config)
            from module.device.device import Device
            if (self.config_name == 'oas_leveling' and
                    (self.config.newbie_leveling.scheduler.enable or
                     getattr(self, '_newbie_leveling_active', False))):
                from tasks.NewbieLeveling.device import LevelingDevice as Device
            device = Device(config=self.config)
            return device
        except RequestHumanTakeover:
            if self.config_name == 'oas_leveling':
                raise
            logger.critical('Request human takeover')
            exit(1)
        except Exception as e:
            if self.config_name == 'oas_leveling':
                raise
            logger.exception(e)
            exit(1)

    @cached_property
    def checker(self):
        """
        占位函数，在alas中是检查服务器是否正常的
        :return:
        """
        return None

    def save_error_log(self):
        """
        Save last 60 screenshots in ./log/error/<timestamp>
        Save logs to ./log/error/<timestamp>/log.txt
        """
        from module.base.utils import save_image
        from module.handler.sensitive_info import (handle_sensitive_image,
                                                   handle_sensitive_logs)
        if self.config.script.error.save_error:
            if not os.path.exists('./log/error'):
                os.mkdir('./log/error')
            folder_name = str(int(time.time() * 1000))
            folder = f'./log/error/{folder_name}'
            logger.warning(f'Saving error: {folder}')
            logger.info('保存详细错误的日志和截图到路径:')
            logger.info(f'{str( Path.cwd() / "log" / "error" / folder_name)}')
            os.mkdir(folder)
            for data in self.device.screenshot_deque:
                image_time = datetime.strftime(data['time'], '%Y-%m-%d_%H-%M-%S-%f')
                image = handle_sensitive_image(data['image'])
                save_image(image, f'{folder}/{image_time}.png')
            with open(logger.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                start = 0
                for index, line in enumerate(lines):
                    line = line.strip(' \r\t\n')
                    if re.match('^═{15,}$', line):
                        start = index
                lines = lines[start - 2:]
                lines = handle_sensitive_logs(lines)
            with open(f'{folder}/log.txt', 'w', encoding='utf-8') as f:
                f.writelines(lines)

    def init_server(self, port: int) -> int:
        """
        初始化zerorpc服务，返回端口号
        :return:
        """
        self.server = zerorpc.Server(self)
        try:
            self.server.bind(f'tcp://127.0.0.1:{port}')
            return port
        except zmq.error.ZMQError:
            logger.error(f"Ocr server cannot bind on port {port}")
            return None

    def run_server(self) -> None:
        """
        启动zerorpc服务
        :return:
        """
        self.server.run()

    def gui_args(self, task: str) -> str:
        """
        获取给gui显示的参数
        :return:
        """
        return self.config.gui_args(task=task)

    def gui_menu(self) -> str:
        """
        获取给gui显示的菜单
        :return:
        """
        return self.config.gui_menu

    def gui_task(self, task: str) -> str:
        """
        获取给gui显示的任务 的参数的具体值
        :return:
        """
        return self.config.model.gui_task(task=task)

    def gui_set_task(self, task: str, group: str, argument: str, value) -> bool:
        """
        设置给gui显示的任务 的参数的具体值
        :return:
        """
        # 验证参数
        task = convert_to_underscore(task)
        group = convert_to_underscore(group)
        argument = convert_to_underscore(argument)
        # pandtic验证
        if isinstance(value, str):
            if len(value) == 8:
                try:
                    value = datetime.strptime(value, '%H:%M:%S').time()
                except ValueError:
                    pass


        path = f'{task}.{group}.{argument}'
        task_object = getattr(self.config.model, task, None)
        group_object = getattr(task_object, group, None)
        argument_object = getattr(group_object, argument, None)

        if argument_object is None:
            logger.error(f'Set arg {task}.{group}.{argument}.{value} failed')
            return False

        try:
            setattr(group_object, argument, value)
            argument_object = getattr(group_object, argument, None)
            logger.info(f'Set arg {task}.{group}.{argument}.{argument_object}')
            self.config.save()  # 我是没有想到什么方法可以使得属性改变自动保存的
            return True
        except ValidationError as e:
            logger.error(e)
            return False

    @zerorpc.stream
    def gui_mirror_image(self):
        """
        获取给gui显示的镜像
        :return: cv2的对象将 numpy 数组转换为字节串。接下来MsgPack 进行序列化发送方将图像数据转换为字节串
        """
        # return msgpack.packb(cv2.imencode('.jpg', self.device.screenshot())[1].tobytes())
        img = cv2.cvtColor(self.device.screenshot(), cv2.COLOR_RGB2BGR)
        self.device.stuck_record_clear()
        ret, buffer = cv2.imencode('.jpg', img)
        yield buffer.tobytes()

    def _gui_update_tasks(self) -> None:
        """
        获取更新任务后 pending waiting 的任务 和 当前的任务的数据。打包给gui显示
        :return:
        """
        data = {}
        pending = []
        waiting = []
        task = {}
        if self.config.task is not None and self.config.task.next_run < datetime.now():
            task["name"] = self.config.task.command
            task["next_run"] = str(self.config.task.next_run)
        data["task"] = task

        for p in self.config.pending_task[1:]:
            item = {"name": p.command, "next_run": str(p.next_run)}
            pending.append(item)

        for w in self.config.waiting_task:
            item = {"name": w.command, "next_run": str(w.next_run)}
            waiting.append(item)


        data["pending"] = pending
        data["waiting"] = waiting

        if self.gui_update_task is not None:
            self.gui_update_task(data)

    def _gui_set_status(self, status: str) -> None:
        """
        设置给gui显示的状态
        :param status: 可以在gui中显示的状态 有 "Init", "Empty"(不显示), "Run"(运行中), "Error", "Free"(空闲)
        :return:
        """
        data = {"status": status}
        if self.gui_update_task is not None:
            self.gui_update_task(data)

    def gui_task_list(self) -> str:
        """
        获取给gui显示的任务列表
        :return:
        """
        result = {}
        for key, value in self.config.model.dict().items():
            if isinstance(value, str):
                continue
            if key == "restart":
                continue
            if "scheduler" not in value:
                continue

            scheduler = value["scheduler"]
            item = {"enable": scheduler["enable"],
                    "next_run": str(scheduler["next_run"])}
            key = self.config.model.type(key)
            result[key] = item
        return json.dumps(result)

    def _release_token_before_wait(func):
        @wraps(func)
        def wrapper(self, future, *args, **kwargs):
            if self.instance_guard and self.instance_guard.should_release(
                pending_task=self.config.pending_task,
                waiting_task=self.config.waiting_task,
                idle_threshold_minutes=self.config.script.optimization.queue_idle_threshold
            ):
                self.instance_guard.release()
            return func(self, future, *args, **kwargs)
        return wrapper

    @_release_token_before_wait
    def wait_until(self, future, monitor_invites=False):
        """
        Wait until a specific time.

        Args:
            future (datetime):

        Returns:
            bool: True if wait finished, False if config changed.
        """
        future = future + timedelta(seconds=1)
        self.config.start_watching()
        if monitor_invites:
            logger.info('Idle cooperation invitation monitoring enabled (every 5 seconds)')
        while 1:
            if datetime.now() > future:
                return True
            # if self.stop_event is not None:
            #     if self.stop_event.is_set():
            #         logger.info("Update event detected")
            #         logger.info(f"[{self.config_name}] exited. Reason: Update")
            #         exit(0)

            time.sleep(5)

            if self.config.should_reload():
                return False

            if monitor_invites:
                try:
                    self._check_idle_invitation()
                    self._idle_connection_failures = 0
                except (RequestHumanTakeover, EmulatorNotRunningError, ConnectionError) as error:
                    failures = getattr(self, '_idle_connection_failures', 0) + 1
                    self._idle_connection_failures = failures
                    logger.warning(f'Idle monitoring unavailable ({failures}/3): {error}; emulator unchanged')
                    if failures >= 3:
                        monitor_invites = False
                        logger.warning('Idle monitoring paused after 3 failures; scheduler remains alive')

    def _check_idle_invitation(self):
        # Use the same reward policy as active tasks, without starting the game
        # or navigating away from the page selected for idle waiting.
        if self._emulator_down or not self.device.app_is_running():
            return False
        from tasks.base_task import BaseTask
        handler = getattr(self, '_idle_invitation_handler', None)
        if handler is None or handler.config is not self.config:
            handler = BaseTask(self.config, self.device)
            self._idle_invitation_handler = handler
        # Waiting is intentional; its elapsed time must not trip the active
        # task's stuck detector when the next screenshot is captured.
        self.device.stuck_record_clear()
        self.device.screenshot()
        handled = handler._burst(preserve_unknown=True)
        self.device.stuck_record_clear()
        return handled

    def get_next_task(self) -> str:
        """
        获取下一个任务的名字, 大驼峰。
        :return:
        """
        while True:
            task = self.config.get_next()
            self.config.task = task
            if self.state_queue:
                self.state_queue.put({"schedule": self.config.get_schedule_data()})
            now = datetime.now()
            if not self._try_acquire_queue_token():
                del_cached_property(self, "config")
                continue
            # 任务时间到了返回任务名称
            if task.next_run <= now:
                return task.command
            # 根据策略执行等待逻辑
            if not self._handle_wait_during_idle(task.next_run):
                # 若等待被打断, 则刷新配置
                del_cached_property(self, "config")

    def _try_acquire_queue_token(self) -> bool:
        """
        尝试获取排队执行权。
        如果排队模式未启用，返回 True。
        如果排队模式启用但未能获取到执行权，进入等待循环直到获取成功或配置变更。

        Returns:
            True: 获取得执行权，可以执行任务
            False: 等待被配置变更打断，调用方应重新加载配置后重试
        """
        # 是否开启排队模式
        if not self.config.script.optimization.queue_mode:
            if self.instance_guard:
                self.instance_guard.remove_from_queue()
                self.instance_guard = None
            return True

        # 懒加载instance_guard
        if self.instance_guard is None:
            try:
                self.instance_guard = InstanceGuard(self.config_name)
                logger.info(f"[Queue] Queue mode enabled for '{self.config_name}'")
            except Exception:
                self.instance_guard = None
                return True

        # 尝试获取执行权
        if self.instance_guard.try_acquire():
            return True

        # 执行权获取失败，关闭模拟器并进入等待循环
        logger.info(f"[Queue] '{self.config_name}' waiting for execution token (emulator stays running)")
        self.config.start_watching()
        while True:
            time.sleep(30)

            if self.config.should_reload():
                logger.info(f"[Queue] Config changed, re-evaluating")
                return False

            if self.instance_guard.try_acquire():
                return True

    def _handle_wait_during_idle(self, next_run: datetime) -> bool:
        """
        处理任务空闲期间的行为策略
        :param next_run: 下一个任务的时间
        :return: True 表示等待成功完成, False 表示等待被中断
        """
        method = self.config.script.optimization.when_task_queue_empty
        strategy_map = {
            "close_game": self._wait_close_game,
            "goto_main": self._wait_goto_main,
        }
        func = strategy_map.get(method)
        if func is None:
            logger.warning(f"Invalid Optimization_WhenTaskQueueEmpty: {method}, fallback to stay_there")
            func = self._wait_stay_there
        return func(next_run)

    @staticmethod
    def _time_to_timedelta(value) -> timedelta:
        if value is None:
            return timedelta(0)
        return timedelta(hours=value.hour, minutes=value.minute, seconds=value.second)

    def _wait_until_with_emulator_preheat(self, next_run: datetime) -> bool:
        """Wait until next_run; if emulator is down, preheat startup before next task."""
        if not self._emulator_down:
            return self.wait_until(next_run)

        startup_lead = self._time_to_timedelta(self.config.script.optimization.emulator_startup_lead_time)
        now = datetime.now()
        wake_time = next_run - startup_lead if startup_lead > timedelta(0) else next_run
        if wake_time < now:
            wake_time = now

        now = datetime.now()
        if wake_time > now:
            logger.info(f"Wait before wake emulator: {wake_time.strftime('%Y-%m-%d %H:%M:%S')}")
            if not self.wait_until(wake_time):
                return False

        if self._emulator_down:
            # Emulator start is manual-only; never wake it automatically.
            logger.warning("Emulator was stopped outside this script; waiting for the user to start it")
            self._emulator_down = False
            self.device = Device(self.config)

        if wake_time < next_run:
            return self.wait_until(next_run)
        return True

    def _wait_close_game(self, next_run: datetime) -> bool:
        if self._emulator_down:
            logger.info("Emulator is down, skip close_game/goto_main action and wait with preheat")
            return self._wait_until_with_emulator_preheat(next_run)

        close_game_wait_duration = self.config.script.optimization.close_game_wait_duration
        close_game_wait = self._time_to_timedelta(close_game_wait_duration)
        close_emulator_wait_duration = self.config.script.optimization.close_emulator_wait_duration
        close_emulator_wait = self._time_to_timedelta(close_emulator_wait_duration)

        if close_emulator_wait > timedelta(0) and next_run > datetime.now() + close_emulator_wait:
            logger.warning("Close emulator is disabled; wait with the emulator running")
            self.device.release_during_wait()
            return self.wait_until(next_run)

        if close_game_wait <= timedelta(0):
            logger.info("Close game during wait")
            self.device.app_stop()
            self.device.release_during_wait()
            if not self.wait_until(next_run):
                return False
            self.run("Restart")
            return True

        if next_run > datetime.now() + close_game_wait:
            logger.info("Close game during wait")
            self.device.app_stop()
            self.device.release_during_wait()
            if not self.wait_until(next_run):
                return False
            self.run("Restart")
            return True

        logger.info("Wait without closing game (close_game wait duration not reached)")
        self.device.release_during_wait()
        if not self.wait_until(next_run):
            return False
        return True

    def _wait_goto_main(self, next_run: datetime) -> bool:
        if self._emulator_down:
            logger.info("Emulator is down, skip goto_main and wait with preheat")
            return self._wait_until_with_emulator_preheat(next_run)

        close_emulator_wait_duration = self.config.script.optimization.close_emulator_wait_duration
        close_emulator_wait = self._time_to_timedelta(close_emulator_wait_duration)
        if close_emulator_wait > timedelta(0) and next_run > datetime.now() + close_emulator_wait:
            logger.warning("Close emulator is disabled; wait with the emulator running")
            self.device.release_during_wait()
            return self.wait_until(next_run)

        logger.info("Goto main page during wait")
        self.run("GotoMain")
        self.device.release_during_wait()
        return self.wait_until(next_run, monitor_invites=True)

    def _wait_stay_there(self, next_run: datetime) -> bool:
        if self._emulator_down:
            logger.info("Stay_there during wait (emulator is down, with preheat)")
            return self._wait_until_with_emulator_preheat(next_run)

        logger.info("Stay_there (no action) during wait")
        self.device.release_during_wait()
        return self.wait_until(next_run, monitor_invites=True)

    def exception_handler(self, e: Exception, command: str) -> None:
        # 处理御魂溢出
        from tasks.Utils.post_diagnotor import PostDiagnotor, AnalyzeType
        image = getattr(self.device, 'image', None)
        # image为None则不做处理
        if image is None:
            return
        analyse_type = PostDiagnotor().handle(e=e, command=command, image=image)
        if analyse_type == AnalyzeType.SoulOverflow:
            self.config.task_call('SoulsTidy')
            time.sleep(1)

    def _restart_game_after_failure(self, command: str, wait_seconds: int = 10) -> bool:
        """Restart the game immediately and prove that capture/login recovered.

        ``Restart`` is a disabled scheduler entry in normal user profiles, so
        merely moving its ``next_run`` cannot make it runnable.  Error recovery
        must therefore be independent of that scheduler flag.  Keep this path
        bounded: one app restart is attempted for each failed task invocation;
        the scheduler's existing failure budget handles repeated failures.
        """
        logger.warning(
            f'Recover `{command}` by restarting {self.device.package} '
            f'in {wait_seconds} seconds')
        if wait_seconds > 0:
            self.device.sleep(wait_seconds)

        try:
            from tasks.Restart.login import LoginHandler

            self.device.stuck_record_clear()
            self.device.click_record_clear()
            self.device.app_stop()
            self.device.sleep(2)
            self.device.app_start()

            # Use the bounded, non-harvest login primitive.  app_handle_login()
            # owns another restart loop, which would make this recovery path
            # unbounded when window capture remains black.
            login = LoginHandler(config=self.config, device=self.device)
            login._app_handle_login()

            # Login markers already require visible frames, but take one fresh
            # sample as an explicit postcondition before retrying the task.
            self.device.screenshot()
            if self.device.last_screenshot_black:
                raise GameBlackScreenError(
                    'Pure-black UI capture after game restart')
        except Exception as restart_error:
            logger.exception(restart_error)
            logger.error(
                f'Game restart did not recover `{command}`; '
                'leave the failure to the bounded scheduler retry')
            return False

        logger.info(
            f'Game restart recovered `{command}`; retry with a new task instance')
        return True

    def _report_final_failure(self, command, error, reason='recovery_exhausted'):
        from module.handler.failure_report import report_script_failure
        self._final_failure_reported = True
        return report_script_failure(self, command, error, reason=reason)

    def _handle_recoverable_failure(self, command, error, wait_seconds=10):
        """Two restart attempts, then hand off. Login recovery is NOT task success.

        The existing scheduler remains responsible for selecting a new task
        invocation. Keep the budget here so config reloads cannot reset it.
        Local back/re-entry is not added here: safe navigation is task-specific.
        """
        from collections import deque
        records = self.__dict__.setdefault('_task_failures', {})
        record = records.setdefault(command, {'attempts': 0, 'recoveries': []})
        record['attempts'] += 1
        record['error'] = error
        record['stage'] = self.__dict__.get('_active_stage', command)
        device = self.__dict__.get('device')
        if device is not None:
            image = vars(device).get('image')
            if image is not None:
                history = self.__dict__.setdefault('_failure_images', {}).setdefault(command, deque(maxlen=3))
                history.append(image.copy())
        if record['attempts'] >= 3 or not self.config.script.error.handle_error:
            self._report_final_failure(command, error)
            self._script_end_requested = True
            return False
        try:
            self.exception_handler(e=error, command=command)
        except Exception as diagnosis_error:
            logger.warning('Post diagnosis failed: %s', type(diagnosis_error).__name__)
        recovered = self._restart_game_after_failure(command, wait_seconds=wait_seconds)
        record['recoveries'].append({'kind': 'game_restart', 'attempt': record['attempts'],
                                     'recovered': bool(recovered)})
        # A successful relogin must not reset failure_record in loop().
        return False

    def run(self, command: str) -> bool:
        """
        :param command:  大写驼峰命名的任务名字
        :return:
        """
        if command == 'NewbieLeveling':
            # New-account screens must never enter the mature-account login,
            # harvest, queue recovery or automatic Restart paths below.
            try:
                from tasks.NewbieLeveling.script_task import ScriptTask
                ScriptTask.validate_profile(self.config)
                self._newbie_leveling_active = True
                # Never reuse a normal device if a direct leveling invocation
                # follows another operation on the same Script instance.
                if isinstance(self.__dict__.get('device'), Device):
                    del_cached_property(self, 'device')
                ScriptTask(config=self.config, device=self.device).run()
            except ScriptEnd as e:
                logger.info(f'Script requested a bounded stop: {e}')
                stop_error = e.__cause__ or e.__context__
                if stop_error is not None and not isinstance(stop_error, (TaskEnd, ScriptEnd)):
                    self._report_final_failure(command, stop_error, reason='task_stopped')
            except Exception as e:
                logger.exception(e)
                logger.error('NewbieLeveling stopped without automatic recovery')
                self._report_final_failure(command, e, reason='protected_stop')
            self._script_end_requested = True
            return True

        if command == 'start' or command == 'goto_main':
            logger.error(f'Invalid command `{command}`')

        if not self._try_acquire_queue_token():
            return False

        if self.instance_guard and self.instance_guard.token_lost:
            logger.warning(f'Token lost, rejoining queue with the emulator left running')
            self.instance_guard.release()
            return False

        try:
            self.device.screenshot()
            module_name = 'script_task'
            module_path = str(Path.cwd() / 'tasks' / command / (module_name+'.py'))
            logger.info(f'module_path: {module_path}, module_name: {module_name}')
            task_module = load_module(module_name, module_path)
            try:
                task_instance = task_module.ScriptTask(config=self.config, device=self.device)
                self._active_stage = command
                try:
                    task_instance.run()
                finally:
                    stage = getattr(task_instance, 'stage', command)
                    self._active_stage = stage if isinstance(stage, str) else command
            except GameSessionExpiredError as e:
                logger.warning(e)
                logger.info(f'Relogin before retrying interrupted task `{command}`')
                from tasks.Restart.login import LoginHandler
                self.device.stuck_record_clear()
                self.device.click_record_clear()
                # Keep real login failures inside the normal exception boundary.
                LoginHandler(config=self.config, device=self.device).app_handle_login()
                # GotoMain is an idle helper, not a configurable scheduled task.
                if command != 'GotoMain':
                    self.config.task_call(command, force_call=False)
                logger.info(f'Relogin complete; retry `{command}` with a new task instance')
                return True
            return True
        except ScriptEnd as e:
            logger.info(f'Script requested a bounded stop: {e}')
            stop_error = e.__cause__ or e.__context__
            if stop_error is not None and not isinstance(stop_error, (TaskEnd, ScriptEnd)):
                self._report_final_failure(command, stop_error, reason='task_stopped')
            self._script_end_requested = True
            return True
        except TaskEnd:
            return True
        except GameNotRunningError as e:
            logger.warning(e)
            return self._handle_recoverable_failure(command, e, wait_seconds=0)
        except (GameStuckError, GameTooManyClickError, GameBugError, GamePageUnknownError) as e:
            logger.error(e)
            return self._handle_recoverable_failure(command, e)
        except (ScriptError, RequestHumanTakeover) as e:
            logger.critical(e)
            self._report_final_failure(command, e, reason='protected_stop')
            exit(1)
        except Exception as e:
            logger.exception(e)
            self._report_final_failure(command, e, reason='code_exception')
            exit(1)

    def loop(self):
        """
        Main loop of scheduler.
        :return:
        """
        with _log_switch_lock:
            logger.set_file_logger(self.config_name, do_cleanup=True)
        start_day = date.today()
        logger.info(f'Start scheduler loop: {self.config_name}')
        self.config.model.running_task = ''

        # Update GUI 防呆, 读取设置并立刻显示后台模拟器到前台
        if not self.config.script.device.run_background_only and IS_WINDOWS:
            from module.device.platform2.platform_windows import minimize_by_name, show_window_by_name
            target_window_name = self.config.script.device.handle  # 在这里输入你的具体窗口名称
            if self.config.script.device.emulator_window_minimize:
                minimize_by_name(target_window_name)
                logger.info(f'重新显示: {target_window_name}')
            else:
                show_window_by_name(target_window_name)
                
        while 1:
            if date.today() > start_day:
                with _log_switch_lock:
                    logger.set_file_logger(self.config_name, do_cleanup=True)
                start_day = date.today()
            # Check update event from GUI
            # if self.stop_event is not None:
            #     if self.stop_event.is_set():
            #         logger.info("Update event detected")
            #         logger.info(f"Alas [{self.config_name}] exited.")
            #         break

            # Check game server maintenance
            # self.checker.wait_until_available()
            # if self.checker.is_recovered():
            #     # There is an accidental bug hard to reproduce
            #     # Sometimes, config won't be updated due to blocking
            #     # even though it has been changed
            #     # So update it once recovered
            #     del_cached_property(self, 'config')
            #     logger.info('Server or network is recovered. Restart game client')
            #     self.config.task_call('Restart')

            # Get task
            task = self.get_next_task()
            # Skip first restart
            if self.is_first_task and task == 'Restart':
                logger.info('Skip task `Restart` at scheduler start')
                self.config.task_delay(task='Restart', success=True, server=True)
                del_cached_property(self, 'config')
                continue

            if task == 'NewbieLeveling':
                # Validate the isolated profile in run() before Device exists.
                pass
            elif self._emulator_down:
                self.device = Device(self.config)
                self._emulator_down = False
            else:
                _ = self.device

            # Run
            logger.info(f'Scheduler: Start task `{task}`')
            if task != 'NewbieLeveling':
                self.device.stuck_record_clear()
                self.device.click_record_clear()
            logger.hr(task, level=0)
            self.config.model.running_task = task
            success = self.run(inflection.camelize(task))
            self.config.model.running_task = ''
            logger.info(f'Scheduler: End task `{task}`')
            self.is_first_task = False
            if getattr(self, '_script_end_requested', False):
                logger.info('Scheduler stopped normally by task request')
                break

            # Check failures
            # failed = deep_get(self.failure_record, keys=task, default=0)
            failed = self.failure_record[task] if task in self.failure_record else 0
            failed = 0 if success else failed + 1
            # deep_set(self.failure_record, keys=task, value=failed)
            self.failure_record[task] = failed
            if failed >= 3:
                logger.critical(f"Task `{task}` failed 3 or more times.")
                logger.critical("Possible reason #1: You haven't used it correctly. "
                                "Please read the help text of the options.")
                logger.critical("Possible reason #2: There is a problem with this task. "
                                "Please contact developers or try to fix it yourself.")
                logger.critical('Request human takeover')
                # 添加失败三次的推送通知
                self._report_final_failure(task, RuntimeError('Task failed three times'), reason='scheduler_exhausted')
                # 关闭模拟器
                if self.config.script.error.error_repeated:
                    logger.critical('Emulator shutdown is disabled; leaving the emulator running')
                exit(1)

            if success:
                self.__dict__.get('_task_failures', {}).pop(task, None)
                self.__dict__.get('_failure_images', {}).pop(task, None)
                del_cached_property(self, 'config')
                continue
            elif self.config.script.error.handle_error:
                # self.config.task_delay(success=False)
                del_cached_property(self, 'config')
                # self.checker.check_now()
                continue
            else:
                break

    def start_loop(self) -> None:
        """
        创建一个线程，运行loop
        :return:
        """
        if self.loop_thread is None:
            self.loop_thread = Thread(target=self.loop, name='Script_loop')
            self.loop_thread.start()


if __name__ == "__main__":
    ensure_ocr_server_started()
    script = Script("oas1")
    script.loop()
