import importlib
from time import sleep
from datetime import datetime, timedelta

from module.exception import TaskEnd, RequestHumanTakeover, GameStuckError, GameTooManyClickError, GameSessionExpiredError, GamePageUnknownError
from module.logger import logger
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.FindJade import WantedQuestsEx
from tasks.FindJade import black_gold
from tasks.FindJade import board_scan
from tasks.FindJade import assist
from tasks.FindJade.assets import FindJadeAssets
from tasks.FindJade.config import AccountInfo, FindJade
from tasks.FindJade.report import CooperationReport
from tasks.GameUi.game_ui import GameUi
from tasks.WantedQuests.config import CooperationType


class ScriptTask(GameUi, FindJadeAssets):
    fade_conf: FindJade= None

    @staticmethod
    def refresh_period(now):
        if now.hour >= 18:
            return now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now.hour >= 5:
            return now.replace(hour=5, minute=0, second=0, microsecond=0)
        return (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)

    def run(self):
        # The scheduler reloads this task file, but imported adapters remain cached
        # in the long-lived worker. Refresh them at the task boundary so fixes
        # take effect on the next scheduled run without restarting the worker.
        importlib.reload(black_gold)
        importlib.reload(board_scan)
        importlib.reload(WantedQuestsEx)
        importlib.reload(assist)
        self.fade_conf = self.config.find_jade
        self.cooperation_report = CooperationReport(self.config.config_name)
        self.report_status = '异常结束（仅包含已识别结果）'
        try:
            self.run_find_jade()
        except RequestHumanTakeover:
            self.report_status = '需要人工处理（仅包含已识别结果）'
            raise
        finally:
            # Preserve partial results even when task execution raises TaskEnd
            # or an error. A notification failure must not mask the game error.
            try:
                self.cooperation_report.finish(self.report_status)
                self.push_cooperation_report()
            except Exception as error:
                logger.exception('Failed to finalize cooperation report')
                self.cooperation_report.notification = '汇总处理失败：' + type(error).__name__
                try:
                    self.cooperation_report.flush()
                except Exception:
                    logger.exception('Failed to save report finalization error')

    def create_wanted_quests(self, account):
        wq = self.CreatObjectFromModule('WantedQuests', config=self.config, device=self.device)
        wq.fade_conf = self.fade_conf
        wq.support_account = account
        wq.cooperation_report = self.cooperation_report
        return wq

    def push_cooperation_report(self):
        report = self.cooperation_report
        error = self.config.model.script.error
        if not self.fade_conf.find_jade_config.report_notify_enable or not error.notify_enable:
            report.notification = '未启用推送；已保存本地记录'
            report.flush()
            return
        from module.notify.notify import Notifier
        notifier = Notifier(error.notify_config, True)
        notifier.config_name = self.config.config_name.upper()
        parts = report.messages()
        report.notification = '准备推送'
        report.flush()
        for index, content in enumerate(parts, 1):
            if index > 1:
                sleep(3)
            title = '协作任务汇总' + (f'（{index}/{len(parts)}）' if len(parts) > 1 else '')
            if not notifier.push(title=title, content=content):
                report.notification = f'第 {index}/{len(parts)} 段推送失败；本地记录已保存'
                report.flush()
                logger.warning(report.notification)
                return
            report.notification = f'已提交 {index}/{len(parts)} 段；未确认微信送达'
            report.flush()

    def run_find_jade(self):
        scan_period = self.refresh_period(datetime.now())
        scanned_accounts = set()
        deferred_accounts = set()
        scan_complete = True
        had_errors = False
        consecutive_hard_failures = 0
        accounts = [account for account in self.fade_conf.sup_account_list if account.is_valid()]
        if not accounts:
            logger.warning('FindJade has no valid support accounts configured')
            self.next_run('FindJade', success=False)
            raise TaskEnd('FindJade')
        for account in accounts:
            if self.cooperation_report.account_key(account) not in self.cooperation_report.accounts:
                self.cooperation_report.account_status(account, '尚未扫描')
        logger.info('Full cooperation scan begins: %s support accounts; real-world quests are recorded only', len(accounts))
        for account_index, accountInfo in enumerate(accounts, 1):
            previous = self.cooperation_report.accounts.get(self.cooperation_report.account_key(accountInfo), {})
            deferred = self.cooperation_report.sender_pending(accountInfo)
            if deferred and all(event.get('sender_deferred') for event in deferred):
                self.cooperation_report.account_status(accountInfo, '协作待完成，暂跳过以继续扫描其他账号')
                deferred_accounts.add(account_index)
                logger.warning('Resume: preserve deferred sender work for %s and continue scan', accountInfo.character)
                continue
            if previous.get('status') == '扫描完成' and not self.cooperation_report.sender_pending(accountInfo):
                scanned_accounts.add(account_index)
                logger.info('Resume: skip completed account %s (%s/%s)', accountInfo.character, account_index, len(accounts))
                continue
            logger.info("start %s-%s (%s/%s)", accountInfo.character, accountInfo.svr, account_index, len(accounts))
            run_normal = self.is_need_login(accountInfo)
            account_scanned = False
            try:
                self.cooperation_report.account_status(accountInfo, '切换账号中')
                if not self.switch_support_account(accountInfo):
                    raise GameStuckError(f'Cannot switch to support account {accountInfo.character}')
                wq = self.create_wanted_quests(accountInfo)
                # Record all requested categories, including tasks that will
                # not be invited because of preferences or recipient history.
                if not wq.open_cooperation_board():
                    raise GameStuckError('Cannot confirm cooperation board; real-world scan incomplete')
                items = wq.read_cooperation_info(inspect_realworld=True)
                realworld_count = sum(item['type'] == CooperationType.RealWorld for item in items)
                logger.info('Recorded %s real-world quests for %s; automatic real-world invitations are disabled',
                            realworld_count, accountInfo.character)
                account_scanned = True
                scanned_accounts.add(account_index)
                self.cooperation_report.account_status(accountInfo, '扫描完成，正在处理协作')
                pending = self.cooperation_report.sender_pending(accountInfo)
                if pending:
                    if not all(event.get('sender_tracked') for event in pending):
                        shared=[item for item in items if item.get('already_shared') and not item.get('completed') and item['type'] != CooperationType.RealWorld]
                        if len(pending)!=1 or len(shared)!=1:
                            raise RequestHumanTakeover('Cannot uniquely match pending invitation to shared quest')
                        if not wq.trace_one(shared[0]['inviteBtn']):
                            raise GameStuckError('Cannot confirm tracking for pending invitation')
                        pending[0]['sender_tracked']=True
                        self.cooperation_report.flush()
                    self.cooperation_report.account_status(accountInfo, '继续完成小号协作部分')
                    # Persist proven unproductive routes with the pending
                    # invitation so an interrupted run does not repeat them.
                    wq.sender_excluded_routes = {
                        (route['kind'], route['destination'])
                        for event in pending for route in event.get('excluded_routes', [])
                        if route.get('kind') and route.get('destination')}
                    wq.finish_sender_cooperation()
                    self.cooperation_report.sender_finished(accountInfo)
                    if not wq.open_cooperation_board():
                        raise GameStuckError('Cannot return to board after sender completion')
                if run_normal:
                    # The wrapper excludes every real-world quest from invitations.
                    if any(not item.get('already_shared') and item['type'] != CooperationType.RealWorld and
                           self.fade_conf.get_invite_name(item['type']) for item in items):
                        wq.prepare_sender_cooperation()
                        wq.all_cooperation_invite()
                    pending = self.cooperation_report.sender_pending(accountInfo)
                    if pending:
                        if not all(event.get('sender_tracked') for event in pending):
                            raise RequestHumanTakeover('Invitation sent but sender tracking is incomplete')
                        self.cooperation_report.account_status(accountInfo, '正在完成小号协作部分')
                        wq.finish_sender_cooperation()
                        self.cooperation_report.sender_finished(accountInfo)
                    self.fade_conf.update_account_login_history(accountInfo)
                    self.save_config()
                self.cooperation_report.account_status(accountInfo, '扫描完成')
                wq.ui_click_until_disappear(wq.I_UI_BACK_RED)
            except WantedQuestsEx.SenderBattleFailed as error:
                # A confirmed defeat must not be retried automatically, but
                # should not prevent scanning unrelated accounts either.
                pending = self.cooperation_report.sender_pending(accountInfo)
                if not pending:
                    raise RequestHumanTakeover('战斗失败但无法匹配待完成协作，保留现场') from error
                for event in pending:
                    event['sender_deferred'] = True
                    event['sender_deferred_reason'] = str(error)
                self.cooperation_report.account_status(accountInfo, '战斗失败，协作待完成；继续扫描其他账号')
                deferred_accounts.add(account_index)
                logger.warning('Sender battle failed for %s; preserved pending work without retry', accountInfo.character)
            except RequestHumanTakeover:
                self.cooperation_report.account_status(accountInfo, '需要人工处理')
                raise
            except GameSessionExpiredError as error:
                self.cooperation_report.account_status(accountInfo, '登录失效，已停止并保留未完成任务')
                raise RequestHumanTakeover('Support account session expired; do not skip to another account') from error
            except (GameStuckError, GameTooManyClickError, GamePageUnknownError) as error:
                logger.error('FindJade account %s-%s failed: %s: %s', accountInfo.character, accountInfo.svr, type(error).__name__, error)
                self.cooperation_report.account_status(accountInfo, '异常，安全返回并有限重试：' + type(error).__name__)
                had_errors = True
                scan_complete = False
                if self.recover_account_switch(accountInfo):
                    self.cooperation_report.account_status(accountInfo, '已恢复登录，留待下次扫描')
                    consecutive_hard_failures = 0
                    logger.warning('Continue the scan after recovering %s', accountInfo.character)
                    continue
                consecutive_hard_failures += 1
                self.cooperation_report.account_status(accountInfo, '已跳过，保留现场：' + type(error).__name__ + '：' + str(error))
                if consecutive_hard_failures >= 3:
                    self.cooperation_report.account_status(accountInfo, '连续三个账号无法恢复，需要人工处理')
                    raise RequestHumanTakeover('FindJade cannot recover three consecutive accounts') from error
                logger.warning('Skip %s for this round and continue with the remaining accounts', accountInfo.character)
                continue
            except Exception as e:
                logger.exception(e)
                self.cooperation_report.account_status(accountInfo, '处理失败：' + type(e).__name__)
                had_errors = True
                if not account_scanned:
                    scan_complete = False
        if (not scan_complete or len(scanned_accounts | deferred_accounts) != len(accounts)
                or self.refresh_period(datetime.now()) != scan_period):
            had_errors = True
            logger.warning('Cooperation scan incomplete or refresh boundary crossed; retry later')
        else:
            logger.info('Cooperation scan finished: %s complete, %s deferred, %s total; real-world quests saved without invitations',
                        len(scanned_accounts - deferred_accounts), len(deferred_accounts), len(accounts))
        self.report_status = ('部分失败，已安排重试' if had_errors else
                              '扫描结束，有协作待人工处理' if deferred_accounts else '本轮完成')
        self.next_run("FindJade", success=not had_errors)
        raise TaskEnd("FindJade")

    def switch_support_account(self, account):
        for attempt in range(2):
            try:
                switcher=SwitchAccount(self.config,self.device,account)
                # Bound unknown-page recovery clicks for this account switch.
                close_unknown=switcher.try_close_unknown_page
                close_count=[0]
                def bounded_close_unknown(*args, **kwargs):
                    if close_count[0]>=3:
                        return False
                    clicked=close_unknown(*args, **kwargs)
                    if clicked:
                        close_count[0]+=1
                    return clicked
                switcher.try_close_unknown_page=bounded_close_unknown
                from tasks.FindJade.navigation import SupportServerSwitch
                switcher.C_SA_LOGIN_FORM_SWITCH_SVR_BTN=SupportServerSwitch()
                switcher.server_switch_interval=3
                switcher.server_switch_timeout=20
                switcher.character_list_stable_reads=3
                if account.character=='小傅昊' and account.svr=='极乐砂城':
                    switcher.O_SA_SELECT_SVR_CHARACTER_LIST=black_gold.XiaofuCharacterList()
                else:
                    switcher.O_SA_SELECT_SVR_CHARACTER_LIST=black_gold.SupportCharacterList(account.character,account.svr)
                if switcher.switchAccount(skip_harvest=True):
                    return True
                if not attempt:
                    logger.warning('Could not identify %s; retrying the same account once', account.character)
                    continue
                return False
            except GameSessionExpiredError:
                if attempt:
                    raise
                logger.warning('FindJade session expired while switching %s; retry the same account once', account.character)
            except RequestHumanTakeover as error:
                # Retry only an identity mismatch, once, on the same account.
                if attempt or not str(error).startswith('Character verification failed:'):
                    raise
                logger.warning('Character mismatch while switching %s; retrying the same account once', account.character)
            except GameStuckError as error:
                if attempt or 'Server selector' not in str(error):
                    raise
                logger.warning('Server selector did not settle for %s; retry the same account',account.character)

    def recover_account_switch(self, account):
        """Re-run the account switch a few times; only the game client, never the emulator.

        A login page that cannot load its server list is a network problem, so
        the same switch action is replayed instead of escalating to a restart.
        Returns True when the requested account is active again.
        """
        from tasks.GameUi.page import page_main
        try:
            self.ui_get_current_page()
            self.ui_goto(page_main, timeout=30)
        except Exception as error:
            logger.warning('Safe return failed before retrying %s: %s', account.character, error)
        for attempt in range(2):
            self.device.click_record_clear()
            try:
                if self.switch_support_account(account):
                    logger.warning('Account %s recovered after re-running the switch (%s/2)',
                                   account.character, attempt + 1)
                    return True
            except Exception as error:
                logger.warning('Switch retry %s did not recover %s: %s: %s',
                               attempt + 1, account.character, type(error).__name__, error)
            sleep(5)
        try:
            logger.warning('Restart the game client before retrying %s', account.character)
            self.device.app_stop()
            sleep(5)
            self.device.app_start()
            sleep(20)
            if self.switch_support_account(account):
                logger.warning('Account %s recovered after game restart', account.character)
                return True
        except Exception as error:
            logger.warning('Game restart recovery failed for %s: %s: %s',
                           account.character, type(error).__name__, error)
        return False

    def is_need_login(self, item: AccountInfo):
        """
            根据上次登陆时间 判断是否需要登录查找
        @param item:
        @type item:
        """
        lastTime = item.last_complete_time
        now = datetime.now()
        if now - lastTime > timedelta(hours=13):
            return True
        if (lastTime.hour >= 18 or lastTime.hour < 5) and (18 > now.hour >= 5):
            return True
        if (5 <= lastTime.hour < 18) and now.hour >= 18:
            return True
        return False

    def CreatObjectFromModule(self, task_name: str, **kwargs):
        module_name = 'script_task'
        from pathlib import Path
        module_path = str(Path.cwd() / 'tasks' / task_name / (module_name + '.py'))

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        WQEX = type("WQEX", (module.ScriptTask,), {
            "need_invite_vip": WantedQuestsEx.need_invite_vip,
            "get_invite_vip_name": WantedQuestsEx.get_invite_vip_name,
            "next_run": WantedQuestsEx.next_run,
            "invite_success_callback": WantedQuestsEx.invite_success_callback,
            "get_config": WantedQuestsEx.get_config,
            "get_cooperation_info": WantedQuestsEx.get_cooperation_info,
            "read_cooperation_info": board_scan.read_cooperation_info,
            "original_read_cooperation_info": module.ScriptTask.get_cooperation_info,
            "open_cooperation_board": black_gold.open_cooperation_board,
            "cooperation_is_realworld": black_gold.cooperation_is_realworld,
            "original_cooperation_is_realworld": module.ScriptTask.cooperation_is_realworld,
            "all_cooperation_invite": black_gold.all_cooperation_invite,
            "original_all_cooperation_invite": module.ScriptTask.all_cooperation_invite,
            "cooperation_invite": black_gold.cooperation_invite,
            "original_cooperation_invite": module.ScriptTask.cooperation_invite,
            "cooperation_observer": WantedQuestsEx.cooperation_observer,
            "cooperation_invite_result": WantedQuestsEx.cooperation_invite_result,
            "cooperation_sender_traced": WantedQuestsEx.cooperation_sender_traced,
            "close_cooperation_detail": WantedQuestsEx.close_cooperation_detail,
            "enter_sender_exploration": WantedQuestsEx.enter_sender_exploration,
            "finish_sender_cooperation": WantedQuestsEx.finish_sender_cooperation,
            "find_wq": WantedQuestsEx.find_wq,
            "read_wanted_progress": module.ScriptTask.find_wq,
            "sender_exploration_visible": WantedQuestsEx.sender_exploration_visible,
            "ui_page_appear": WantedQuestsEx.ui_page_appear,
            "original_ui_page_appear": module.ScriptTask.ui_page_appear,
            "wait_until_stable": WantedQuestsEx.wait_until_stable,
            "original_wait_until_stable": module.ScriptTask.wait_until_stable,
            "is_wq_remained": WantedQuestsEx.is_wq_remained,
            "read_wq_remained": module.ScriptTask.is_wq_remained,
            "sender_routes": WantedQuestsEx.sender_routes,
            "sender_tracker_visible": WantedQuestsEx.sender_tracker_visible,
            "sender_challenge_tickets": WantedQuestsEx.sender_challenge_tickets,
            "execute_mission": WantedQuestsEx.execute_mission,
            "battle_before": assist.sender_battle_before,
            "fire": WantedQuestsEx.sender_fire,
            "sender_soul": WantedQuestsEx.sender_soul,
            "close_sender_soul_bonus": WantedQuestsEx.close_sender_soul_bonus,
            "clear_sender_settlement": WantedQuestsEx.clear_sender_settlement,
        })
        wq = WQEX(**kwargs)
        return wq

    def save_config(self):
        # Other tasks may reload Config.model while a support account is active.
        # Reattach the updated invitation ledger before writing it back.
        if self.config.model.find_jade is not self.fade_conf:
            self.config.model.find_jade = self.fade_conf
        self.config.save()

    def next_run(self, task: str, finish: bool = False,
                 success: bool = None, server: bool = True, target: datetime = None) -> None:
        now = datetime.now()
        if success:
            minute = 1 if self.config.config_name == 'oas_leveling' else 5
            if 5 <= now.hour < 18:
                self.set_next_run(task, server=False, target=now.replace(hour=18, minute=minute, second=0, microsecond=0))
            elif now.hour < 5:
                self.set_next_run(task, server=False, target=now.replace(hour=5, minute=minute, second=0, microsecond=0))
            else:
                self.set_next_run(task, server=False, target=now.replace(hour=5, minute=minute, second=0, microsecond=0) + timedelta(days=1))
        else:
            self.set_next_run(task, server=False, target=now + timedelta(minutes=10))


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    # from mypatch import SimplePatch

    # SimplePatch.patch()

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run()
