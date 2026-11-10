"""Create an invitation-only stone room, verify both players, then leave."""
import json, subprocess, psutil, time
from module.config.local_values import local_text
from module.config.config import Config
from module.atom.ocr import RuleOcr
from tasks.TripleAwakening.device import TeamDevice
from tasks.TripleAwakening.script_task import MANAGER
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_team
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Mentorship.private_room import create_private_room
from tasks.Mentorship.normal_device import NormalDevices

inv = json.loads(subprocess.check_output([str(MANAGER), 'info', '-v', 'all']))
cs, ds = [], []
for profile, title in [('oas1','MuMu安卓设备'), ('oas_leveling','MuMu安卓设备-1-1')]:
    c=Config(profile); i=next(x for x in inv.values() if x['name']==title and x['is_android_started'])
    d=c.model.script.device; d.handle=title; d.serial=f"{i['adb_host_ip']}:{i['adb_port']}"
    args=psutil.Process(i['pid']).cmdline(); d.emulatorinfo_name=args[args.index('--vm')+1]
    d.screenshot_method='window_background'; d.control_method='window_message'; d.adb_restart=False
    cs.append(c); ds.append(TeamDevice(c,i))
ui=GameUi(cs[0],ds[0]); ui.ui_get_current_page(); ui.ui_goto_page(page_team,timeout=30)
rooms=GeneralRoom(cs[0],ds[0])
for _ in range(4):
    point=rooms.list_find(rooms.L_TEAM_LIST,'石距',max_swipe=6)
    if point:
        ds[0].click(*point,control_name='mentorship_stone_select'); time.sleep(1); ds[0].screenshot()
        if rooms.O_GR_ZONES_NAME.ocr(ds[0].image).strip().startswith('石距'): break
else: raise RuntimeError('石距未确认')
if not create_private_room(ds[0],'tako'): raise RuntimeError('石距房间创建失败')
r=RuleOcr(roi=(0,0,1280,720),area=(0,0,1280,720),mode='Full',method='Default',keyword='',name='stone_identity')
def read(im):
    result=[]
    for o in r.detect_and_ocr(im):
        x0,y0=int(min(p[0] for p in o.box)),int(min(p[1] for p in o.box))
        x1,y1=int(max(p[0] for p in o.box)),int(max(p[1] for p in o.box))
        result.append((o.ocr_text,(x0,y0,x1-x0,y1-y0)))
    return result
pair=NormalDevices(*ds,local_text('LOCAL_SUPPORT_004'),read_name=read)
try:
    print('STONE_PAIR',pair.invite_and_join('tako'),flush=True)
finally:
    print('STONE_LEFT',pair.leave_both(),flush=True)
