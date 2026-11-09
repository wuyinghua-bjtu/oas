"""Finish each support character's post-awakening collective missions."""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from module.atom.ocr import RuleOcr
from module.exception import GameStuckError
from tasks.CollectiveMissions.assets import CollectiveMissionsAssets as A
from tasks.GuildQuickParticipation.kirin import COURTYARD_GUILD
from tasks.GuildQuickParticipation.policy import select_accounts
from tasks.FindJade.script_task import ScriptTask as FindJadeTask
from tasks.Component.SwitchAccount.login_account import dismiss_new_server_promotion
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.GroupedAwakening.ledger import atomic_json_write
from tasks.GuildQuickParticipation.courtyard import complete_courtyard_affairs, return_from_courtyard_affairs


def finish_account(task, name, data, entry, save):
 d=task.device
 def rule(box,mode='Full'):return RuleOcr(roi=box,area=box,mode=mode,method='Default',keyword='',name='guild_post')
 def words(box):return ''.join(x.ocr_text for x in rule(box).detect_and_ocr(d.image)).replace(' ','')
 def snap():task.screenshot()
 def click(x,y,n,delay=1):d.click(x,y,control_name=n);time.sleep(delay)
 def read_jade_balance():
  readings=[]
  for i in range(2):
   snap()
   text=rule((733,12,58,34),'Single').ocr(d.image).strip().lstrip('_:：').strip()
   digit=rule((733,12,58,34),'Digit').ocr(d.image)
   readings.append((text,digit))
   time.sleep(.2)
  if readings[0]!=readings[1]:
   print('勾玉余额识别不稳定，跳过捐赠',readings,flush=True);return None
  text,digit=readings[0]
  match=re.fullmatch(r'([^0-9]*)([0-9]+)',text)
  if not match:
   print('勾玉余额识别不完整，跳过捐赠',readings,flush=True);return None
  prefix,numerals=match.groups();value=int(numerals)
  if value<100 and digit<100:
   return value
  if prefix or value!=digit:
   print('勾玉余额识别不一致，跳过捐赠',readings,flush=True);return None
  return value
 def clear_reward():
  seen=0
  for i in range(14):
   snap();w=words((390,150,500,145))
   if '获得奖励' in w:seen+=1;click(1000,550,'guild_reward_close');continue
   if seen:return seen
   time.sleep(.5)
  return seen
 # Expand the courtyard scroll before reading currencies or clicking guild.
 # The main-page navigation already verifies and opens the collapsed menu.
 from tasks.GameUi.page import page_main
 task.ui_get_current_page()
 task.ui_goto(page_main)
 for _ in range(3):
  snap()
  if any(label in words((500,585,170,120)) for label in ('阴阳寮','阴阳寨')):
   break
  if task.appear(task.I_MAIN_SCROLL_CLOSE):
   click(1200,650,'guild_expand_courtyard_menu',1.5)
  else:
   time.sleep(1)
 else:
  raise GameStuckError('庭院寮入口未显示，无法安全继续')
 snap();observed=rule((125,25,150,32),'Single').ocr(d.image).strip().replace(' ','');assert observed==name, '角色名不匹配'
 balance=read_jade_balance();entry['jade_before']=balance;save();print('JADE',balance,flush=True)
 if not entry.get('guild_tasks'):
  click(580,644,'guild_open',3)
  # Guild entry can still be animating after the initial delay. Use bounded,
  # fresh observations and known templates, not one OCR sample in a small ROI.
  open_collective_missions(task)
  snap();assert '集体任务' in words((520,30,240,65));n,remain,total=A.O_CM_NUMBER.ocr(d.image);assert total==30 and 0<=n<=30;print('COUNT BEFORE',n,flush=True)
  for x in (640,970):
   snap();label=words((x-80,460,160,65));print('CLAIM',x,label,flush=True)
   if '领取奖励' in label:
    click(x,493,'guild_claim');assert clear_reward()>0,'未确认奖励';d.click_record_clear()
  if n<30:
   previous=None
   for i in range(40):
    snap();w=words((150,125,290,110))
    if previous is not None and w and w!=previous:d.click_record_clear()
    if '高级觉醒材料' in w:break
    previous=w;click(435,509,'refresh_mission')
   else:raise RuntimeError('刷新高级觉醒任务超限')
   snap();n,remain,total=A.O_CM_NUMBER.ocr(d.image);assert total==30 and 0<remain<=30
   click(300,492,'open_awake_material');snap();assert '将提交' in words((500,45,270,65))
   for i in range(remain+12):
    snap();head=words((500,45,270,65));m=re.search(r'将提交(\d+)次',head);assert m,head;selected=int(m.group(1));print('SELECTED',selected,'NEED',remain,flush=True)
    if selected==remain:break
    assert selected<remain
    # Advance only when this material actually increases the selection.
    for y in (166,288,410,532):
     click(929,y,'add_awake_material',.7);snap();new=words((500,45,270,65));q=re.search(r'将提交(\d+)次',new)
     if q and int(q.group(1))==selected+1:
      d.click_record_clear()
      break
    else:
     print('高级材料不足，仅提交已选择数量',selected,flush=True);break
   else:raise RuntimeError('材料选择超限')
   if selected:
    entry['material_submission']='准备提交';save();d.click_record_clear();click(640,627,'submit_awake_material');time.sleep(3);assert clear_reward()>0,'提交后未确认奖励'
    snap();n,remain,total=A.O_CM_NUMBER.ocr(d.image);assert total==30 and 0<=n<=30,(n,remain,total)
   else:
    snap();click(1050,610,'close_material_panel');snap();n,remain,total=A.O_CM_NUMBER.ocr(d.image)
  d.click_record_clear();entry['guild_tasks']=f'{n}/30';entry['awaken_reward']='已检查并领取';entry.pop('material_submission',None);save();print('TASKS',n,'/30',flush=True)
 if 'courtyard_status' not in entry:
  return_to_courtyard(task)
  task.step('觉醒后处理庭院事务 '+name, 180)
  outcome=complete_courtyard_affairs(task.config, d)
  entry['courtyard_status']='完成' if outcome['complete'] else outcome['reason'];save()
  if not return_from_courtyard_affairs(task):raise GameStuckError('庭院事务后未能确认返回庭院')
  task.step('寮勾玉捐赠 '+name, 180)
  balance=read_jade_balance();entry['jade_before']=balance;save()
 if balance is None:
  entry.update(jade_donated=0,jade_status='余额识别不确定，跳过捐赠');save()
 elif balance<100:
  entry.update(jade_donated=0,jade_status='余额不足100，跳过');save();print('DONE LOW',flush=True)
 else:
  return_to_courtyard(task);snap();click(580,644,'guild_open_for_donation',3);snap();click(900,650,'guild_shrine',2);snap();click(1196,160,'guild_information',2);snap()
  # 神社信息页必须同时出现两个特征，防止误点其他加号。
  assert '信息' in words((110,65,130,75)) and '宣言' in words((130,225,345,70)), '未确认寮信息页'
  click(282,508,'open_jade_donation',.2);snap()
  if '本日捐献次数已达上限' in words((380,195,540,100)):
   entry.update(jade_donated=0,jade_status='本日捐献次数已达上限');entry['verified_at']=datetime.now().isoformat(timespec='seconds');save();return
  time.sleep(1.5);snap();assert '阴阳寮捐赠' in words((450,150,380,80))
  for i in range(7):
   snap();count=words((585,285,120,65));cost=words((560,510,170,70))
   if '5/5' in count and '100' in cost:break
   if not re.search(r'[1-4]/5',count):raise GameStuckError(f'捐赠次数未识别：{count}，费用：{cost}')
   click(810,304,'increase_jade_donation',.8)
  else:raise GameStuckError(f'捐赠次数未能达到5次：{count}，费用：{cost}')
  entry['jade_status']='待核对已提交';save();click(640,546,'donate_100_jade',3);assert clear_reward()>0,'捐赠后未确认奖励';entry.update(jade_donated=100,jade_status='已确认奖励');save();print('DONE DONATED',flush=True)
 entry['verified_at']=datetime.now().isoformat(timespec='seconds');save()


def open_collective_missions(task, timeout=25):
    deadline = time.monotonic() + timeout
    clicks = 0
    next_click = 0.0
    while time.monotonic() < deadline:
        task.screenshot()
        if '集体任务' in _words(task, (520,30,240,65)):
            return
        if clicks >= 4 or time.monotonic() < next_click:
            time.sleep(.3)
            continue
        if task.appear(A.I_CM_CM):
            task.appear_then_click(A.I_CM_CM)
        elif task.appear(A.I_CM_SHRINE):
            task.appear_then_click(A.I_CM_SHRINE)
        else:
            time.sleep(.3)
            continue
        clicks += 1
        next_click = time.monotonic() + 2
    task.device.save_screenshot(genre='post_guild_entry', interval=0)
    raise GameStuckError('未确认寮集体任务入口（已有限等待及重试）')


def _words(task, box):
    rule = RuleOcr(roi=box, area=box, mode='Full', method='Default', keyword='', name='post_guild_return')
    return ''.join(row.ocr_text for row in rule.detect_and_ocr(task.device.image)).replace(' ', '')


def return_to_courtyard(task):
    task.step('寮任务后返回庭院', 90)
    for _ in range(16):
        task.screenshot()
        if dismiss_new_server_promotion(task):
            time.sleep(1)
            continue
        if task.appear(task.I_CHECK_MAIN) or task.appear(COURTYARD_GUILD):
            return
        if '已有角色' in SwitchAccountAssets.O_SA_CHECK_SELECT_SVR.ocr_single(task.device.image).replace(' ', ''):
            task.device.click(1104,110,control_name='post_close_character_selector')
            time.sleep(1)
            continue
        if task.appear(task.I_CHECK_LOGIN_FORM):
            from tasks.Restart.login import LoginHandler
            LoginHandler(config=task.config,device=task.device)._app_handle_login()
            continue
        if (task.appear(task.I_CHECK_EXPLORATION)
                and '觉醒材料' in _words(task, (100,610,180,105))
                and task.appear(task.I_UI_BACK_YELLOW)):
            task.appear_then_click(task.I_UI_BACK_YELLOW, interval=2)
        elif '获得奖励' in _words(task, (390,150,500,145)):
            task.device.click(1000,550,control_name='post_close_reward')
        elif '集体任务' in _words(task, (520,30,240,65)):
            task.device.click(1168,120,control_name='post_close_missions')
        elif (task.appear(A.I_CM_SHRINE) or '宣言' in _words(task,(130,225,345,70))
              or '阴界之门' in _words(task,(0,140,245,310))
              or '结界突破' in _words(task,(0,140,245,310))
              or ('集体任务' in _words(task,(140,150,230,80))
                  and any(word in _words(task,(140,400,230,80)) for word in ('狩猎战','阴界之门')))):
            task.device.click(45,38,control_name='post_back_courtyard')
        time.sleep(2)
    raise GameStuckError('寮任务后无法确认返回庭院')


def finish_all(task, config):
    selection = config.model.guild_quick_participation.guild_accounts
    accounts = select_accounts(config.find_jade.sup_account_list, selection.characters, selection.server)
    today = datetime.now().strftime('%Y-%m-%d')
    path = Path('log/GroupedAwakening/oas_leveling') / ('post_guild_' + today + '.json')
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'date':today, 'status':'进行中', 'accounts':{}}
    def save():
        data['updated_at'] = datetime.now().isoformat(timespec='seconds')
        atomic_json_write(path, data)
    guild_path = Path('log/GuildQuickParticipation') / config.config_name / (today + '.json')
    guild_state = json.loads(guild_path.read_text(encoding='utf-8')) if guild_path.exists() else {}
    for account in accounts:
        entry = data['accounts'].setdefault(account.character,{})
        previous_affairs = guild_state.get('accounts', {}).get(account.character, {}).get('庭院事务')
        if previous_affairs and 'courtyard_status' not in entry:
            entry['courtyard_status'] = previous_affairs
            save()
        post_done = bool(entry.get('verified_at') and entry.get('guild_tasks') and (
                entry.get('jade_status') or 'jade_donated' in entry)
                and entry.get('jade_status') != '余额识别不确定，跳过捐赠')
        if post_done and 'courtyard_status' in entry:
            continue
        if entry.get('material_submission') or entry.get('jade_status') == '待核对已提交':
            raise GameStuckError(account.character + ' 上次提交状态未确认，禁止重复提交')
        return_to_courtyard(task)
        task.step('切换并核对 '+account.character, 300)
        if not FindJadeTask.switch_support_account(task, account):
            raise GameStuckError('切换账号失败：'+account.character)
        if not post_done:
            task.step('寮任务及勾玉捐赠 '+account.character, 600)
            finish_account(task, account.character, data, entry, save)
        if 'courtyard_status' not in entry:
            return_to_courtyard(task)
            task.step('觉醒后处理庭院事务 '+account.character, 180)
            outcome = complete_courtyard_affairs(config, task.device)
            entry['courtyard_status'] = '完成' if outcome['complete'] else outcome['reason']
            save()
            if not return_from_courtyard_affairs(task):
                raise GameStuckError('庭院事务后未能确认返回庭院')
    data['status'] = ('完成' if all(e.get('guild_tasks') == '30/30' for e in data['accounts'].values())
                      else '完成（有未满30次）')
    save()
