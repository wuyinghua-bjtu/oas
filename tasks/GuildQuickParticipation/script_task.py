"""Independent guild activity for selected support accounts."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from module.exception import ScriptEnd, TaskEnd, GameStuckError
from module.logger import logger
from tasks.GameUi.game_ui import GameUi
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.FindJade.navigation import SupportServerSwitch
from tasks.GuildQuickParticipation.netherworld import netherworld_and_reward
from tasks.GuildQuickParticipation.policy import select_accounts, activity_for_day, next_start
from tasks.GuildQuickParticipation.courtyard import complete_courtyard_affairs, return_from_courtyard_affairs
from tasks.GuildQuickParticipation.friend import perform_friend_actions
from tasks.GuildQuickParticipation.kirin import kirin_and_reward, COURTYARD_GUILD, leave_guild_after_reward
from tasks.GuildQuickParticipation.notification import notify_result


class ScriptTask(GameUi):
    def run(self):
        if self.config.config_name != 'oas_leveling':
            raise ScriptEnd('Guild task is restricted to oas_leveling')
        now=datetime.now()
        is_kirin=activity_for_day(now)=='kirin'
        activity='狩猎战' if is_kirin else '阴界之门'
        activity_stage=activity+'和领奖'
        selection = getattr(self.config.model.guild_quick_participation, 'guild_accounts', None)
        if selection is None:
            # A running backend can retain the scheduler-only config class.
            # Read the optional selection from disk without restarting it.
            raw = json.loads(Path('config', self.config.config_name + '.json').read_text(encoding='utf-8'))
            selection = raw.get('guild_quick_participation', {}).get('guild_accounts', {})
            accounts = select_accounts(self.config.find_jade.sup_account_list,
                                       selection.get('characters'), selection.get('server', '砂狐乐园'))
        else:
            accounts=select_accounts(self.config.find_jade.sup_account_list, selection.characters, selection.server)
        directory=Path('log/GuildQuickParticipation')/self.config.config_name
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/(now.strftime('%Y-%m-%d')+'.json')
        state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
            'date':now.date().isoformat(),'activity':activity,'accounts':{},'status':'运行中'}
        state['status']='运行中'
        state.pop('failure',None)
        results=[]
        current=''; stage='准备'

        def save():
            state['updated_at']=datetime.now().isoformat(timespec='seconds')
            temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
            temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(path)

        try:
            for account in accounts:
                current=account.character
                entry=state['accounts'].setdefault(current,{})
                if all(name in entry for name in ('点赞和友情点',activity_stage)):
                    for name,status in entry.items():
                        results.append({'character':current,'stage':name,'status':status})
                    continue
                stage='切换账号'
                from tasks.FindJade.script_task import ScriptTask as FindJadeTask
                if not FindJadeTask.switch_support_account(self,account):
                    raise GameStuckError('账号切换未完成')
                if '点赞和友情点' not in entry:
                    stage='点赞和友情点'
                    outcome=perform_friend_actions(self)
                    entry[stage]=outcome['like']+'，'+outcome['friendship']
                    save()
                    self.screenshot()
                    if not self.appear(self.I_UI_BACK_RED):
                        raise GameStuckError('好友界面返回按钮未识别')
                    self.device.click(1178,115,control_name='guild_friend_back')
                    if not self.wait_until_appear(COURTYARD_GUILD,wait_time=20):
                        raise GameStuckError('好友操作后未能确认返回庭院')
                if activity_stage not in entry:
                    stage=activity_stage
                    (kirin_and_reward if is_kirin else netherworld_and_reward)(self, claim=False)
                    entry[stage]='已退出，集体任务奖励待觉醒后领取'
                    save()
                    leave_guild_after_reward(self)
                for name,status in entry.items():
                    results.append({'character':current,'stage':name,'status':status})
            required=('点赞和友情点',activity_stage)
            if not all(all(stage_name in state['accounts'].get(account.character,{})
                           for stage_name in required) for account in accounts):
                raise GameStuckError('仍有账号未处理完全部步骤')
            state['status']='完成'
            save()
            state['notification_sent']=notify_result(self.config,True,results)
            save()
            if self.config.model.guild_quick_participation.scheduler.enable:
                self.set_next_run('GuildQuickParticipation',server=False,target=next_start(datetime.now()))
                # Arm awakening only after every configured guild account has
                # completed all stages. The awakening task disarms itself.
                awakening = self.config.model.grouped_awakening.scheduler
                awakening.next_run = datetime.now().replace(microsecond=0)
                awakening.enable = True
                self.config.save()
                logger.info('小号寮活已完成，已安排分组觉醒')
        except Exception as error:
            state['status']='出错';state['failure']={'character':current,'stage':stage,'reason':str(error)}
            save()
            results.append({'character':current,'stage':stage,'status':'出错'})
            state['notification_sent']=notify_result(self.config,False,results,type(error).__name__)
            save()
            logger.exception(error)
            # Keep the scheduler alive: retry this activity ten minutes later
            # instead of stopping the whole script on a single failed account.
            self.set_next_run('GuildQuickParticipation', server=False,
                              target=datetime.now()+timedelta(minutes=10))
            raise TaskEnd(f'小号寮活动本轮中断：{current} {stage}，稍后自动重试，详情已保存在本地') from error
        raise TaskEnd('GuildQuickParticipation')
