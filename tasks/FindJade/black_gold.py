"""FindJade's October 2026 quest-board skin adapter; never mutates shared assets."""
from time import monotonic
import re

from module.atom.image import RuleImage
from module.atom.click import RuleClick
from module.atom.ocr import RuleOcr
from module.exception import GameStuckError
from module.logger import logger
from tasks.GameUi.page import page_main
from tasks.WantedQuests.assets import WantedQuestsAssets as A
from tasks.WantedQuests.config import CooperationType as T


def rule(file, box, search=None, threshold=.8):
    return RuleImage(roi_front=box,roi_back=search or box,method='Template matching',
                     threshold=threshold,file='./tasks/FindJade/res/'+file)


TITLE=rule('blackgold_title.png',(574,37,136,41),(560,25,160,65))
ALL=rule('blackgold_track_all.png',(1145,585,110,105),(1135,575,130,125))
CANCEL_ALL=rule('blackgold_cancel_all.png',(1145,585,110,105),(1135,575,130,125))
DETAIL_CLOSE=rule('blackgold_detail_close.png',(1190,111,35,35),(1180,100,60,60),.7)
DETAIL_OFF=rule('blackgold_track.png',(1138,548,112,122),(1128,538,132,142))
DETAIL_ON=rule('blackgold_tracked.png',(1138,548,112,122),(1128,538,132,142))
INVITES=[rule('blackgold_invite.png',(154+282*n,398,41,37),
              (90+282*n,390,255,60)) for n in range(4)]
SHARED=[rule('blackgold_shared.png',(316+282*n,401,34,34),
             (90+282*n,390,270,60)) for n in range(4)]
DETAIL_TEXT=RuleOcr(roi=(600,140,570,510),area=(600,140,570,510),mode='Full',
                    method='Default',keyword='',name='blackgold_detail_text')
CARD_TEXT=RuleOcr(roi=(85,390,1120,145),area=(85,390,1120,145),mode='Full',
                  method='Default',keyword='',name='blackgold_card_text')


class RouteField:
    """Read a complete destination row; ornate label borders confuse single-line OCR."""
    def __init__(self,number,field):
        box=(625,272+75*(number-1),420,70)
        self.reader=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',
                            name=f'blackgold_route_{number}_{field}')
        self.field=field

    def ocr(self,image):
        text=''.join(item.ocr_text for item in self.reader.detect_and_ocr(image)).replace(' ','')
        kind=re.search(r'式神碎片|挑战|探索|秘闻|御魂|妖气',text)
        if self.field=='TYPE':
            return kind.group() if kind else ''
        if not kind:
            return ''
        info=re.search(r'(.+?[(（]数量[:：]\s*\d+[)）]?)',text[kind.end():])
        return info.group(1) if info else ''


class ServerSwitchButton(RuleOcr):
    """FindJade-only precise login button with a small verified-click budget."""
    def __init__(self):
        box=(710,485,105,80)
        super().__init__(roi=box,area=box,mode='Full',method='Default',keyword='切换',
                         name='findjade_server_switch')
        self.clicks=0

    def coord(self):
        if self.clicks>=3:
            raise GameStuckError('Server selector did not open after three verified switch-button clicks')
        self.clicks+=1
        x,y,w,h=self.area
        if w<=0 or h<=0:
            raise GameStuckError('Server switch text location was not confirmed')
        return int(x+w/2),int(y+h/2)


class XiaofuCharacterList(RuleOcr):
    """Correct the observed decorative-badge OCR only on the matching server card."""
    def __init__(self):
        box=(418,131,641,481)
        super().__init__(roi=box,area=box,mode='Full',method='Default',keyword='',
                         name='findjade_character_list')

    def detect_and_ocr(self,image,logDisplay=True):
        results=super().detect_and_ocr(image,logDisplay=logDisplay)
        servers=[r for r in results if r.ocr_text=='极乐砂城']
        matches=[]
        for result in results:
            text=result.ocr_text.lstrip('1234567890 ([<>])【】（）《》').replace(' ','')
            if text not in ('小小傅昊','小传昊'):
                continue
            x,y=result.box[0]
            if any(abs(float(x-server.box[0][0]))<100 and
                   50<float(y-server.box[0][1])<105 for server in servers):
                matches.append(result)
        if len(matches)==1:
            matches[0].ocr_text='小傅昊'
            logger.info('Corrected known character-list OCR using matching 极乐砂城 card; verify after login')
        return results


class SupportCharacterList(RuleOcr):
    """Allow one mistaken glyph only when the matching server card is unambiguous."""
    def __init__(self, expected, server):
        box=(418,131,641,481)
        super().__init__(roi=box,area=box,mode='Full',method='Default',keyword='',
                         name='findjade_support_character_list')
        self.expected=expected
        self.server=server

    def detect_and_ocr(self,image,logDisplay=True):
        rows=super().detect_and_ocr(image,logDisplay=logDisplay)
        if any(r.ocr_text.lstrip('1234567890 ([<>])【】（）《》').replace(' ','') == self.expected
               for r in rows):
            return rows
        servers=[r for r in rows if r.ocr_text.replace(' ','')==self.server]
        matches=[]
        suffix=re.search(r'\d+$',self.expected)
        for row in rows:
            text=row.ocr_text.lstrip('1234567890 ([<>])【】（）《》').replace(' ','')
            missing_first = (self.expected.startswith('冥界画师') and
                             text == self.expected[1:])
            if (len(text)!=len(self.expected) and not missing_first) or len(text)<4:
                continue
            if suffix and not text.endswith(suffix.group()):
                continue
            if not missing_first and sum(a!=b for a,b in zip(text,self.expected))!=1:
                continue
            x,y=row.box[0]
            if any(abs(float(x-server.box[0][0]))<100 and
                   50<float(y-server.box[0][1])<105 for server in servers):
                matches.append((row,text))
        if len(matches)==1:
            row,text=matches[0]
            row.ocr_text=self.expected
            logger.info('Possible character OCR %s matched %s on the same server card; verify after login',text,self.expected)
        return rows


def board_visible(self):
    return (not self.appear(DETAIL_CLOSE) and not self.appear(self.I_WQ_INVITE_CANCEL) and
            (self.appear(ALL) or self.appear(CANCEL_ALL)))


def confirmed_ocr_invite(self, button):
    """Recheck an OCR-derived click target on the current board frame."""
    if not isinstance(button, RuleClick) or not button.name.startswith('confirmed_invite_'):
        return False
    if not board_visible(self):
        return False
    x, y, width, _ = button.roi_back
    box = (x, y, width, 145)
    reader = RuleOcr(roi=box, area=box, mode='Full', method='Default', keyword='',
                     name='blackgold_confirm_invite')
    words = ''.join(row.ocr_text for row in reader.detect_and_ocr(self.device.image)).replace(' ', '')
    return '邀请好友' in words


def configure(self):
    if getattr(self,'black_gold_skin',False):
        return
    self.black_gold_skin=True
    # Each instance gets its own rules. Other OAS configurations keep their assets.
    self.I_TRACE_ENABLE=rule('blackgold_track_all.png',(1145,585,110,105),(1135,575,130,125))
    self.I_TRACE_DISABLE=rule('blackgold_cancel_all.png',(1145,585,110,105),(1135,575,130,125))
    self.I_WQ_TRACE_ONE_ENABLE=rule('blackgold_tracked.png',(1138,548,112,122),(1128,538,132,142))
    self.I_WQ_TRACE_ONE_DISABLE=rule('blackgold_track.png',(1138,548,112,122),(1128,538,132,142))
    self.I_TRACE_TRUE=self.I_WQ_TRACE_ONE_ENABLE
    self.I_WQ_TRACE_ONE_CHECK_OPENED=DETAIL_CLOSE
    self.I_WQ_INVITE_SELECTED=rule('blackgold_selected.png',(397,180,32,35),(380,170,350,360))
    self.I_WQ_INVITE_FRIEND_LIST_APPEAR=self.I_WQ_INVITE_ENSURE
    for n,y in enumerate((282,357,432,507),1):
        setattr(self,f'I_GOTO_{n}',rule('blackgold_goto.png',(1060,y,85,35),(1045,y-10,115,60)))
        for kind in ('TYPE','INFO'):
            setattr(self,f'O_WQ_{kind}_{n}',RouteField(n,kind))
    logger.info('FindJade recognized black-gold quest board; installed isolated layout rules')


def open_cooperation_board(self):
    self.screenshot()
    if self.appear(DETAIL_CLOSE):
        configure(self)
        self.close_cooperation_detail()
        if board_visible(self):
            return True
    if board_visible(self):
        configure(self)
        return True
    if not getattr(self,'black_gold_skin',False) and (
            self.appear(self.I_TRACE_ENABLE) or self.appear(self.I_TRACE_DISABLE)):
        return True
    if self.ui_get_current_page()!=page_main:
        self.ui_goto(page_main)
    deadline=monotonic()+35
    clicked_at=None
    while monotonic()<deadline:
        self.screenshot()
        if board_visible(self):
            configure(self)
            return True
        if not getattr(self,'black_gold_skin',False) and (
                self.appear(self.I_TRACE_ENABLE) or self.appear(self.I_TRACE_DISABLE)):
            return True
        if clicked_at is not None and monotonic()-clicked_at<7:
            continue
        if self.appear_then_click(self.I_WQ_SEAL,interval=2):
            clicked_at=monotonic()
            continue
        if self.appear_then_click_multi_scale(self.I_WQ_DONE,scale_range=(.8,1.2),interval=2):
            clicked_at=monotonic()
    self.device.save_screenshot(genre='findjade_unknown_board',interval=1)
    raise GameStuckError('Quest board layout unrecognized; preserved screenshot, not treated as an empty board')


def read_cooperation_info(self,inspect_realworld=False):
    if not getattr(self,'black_gold_skin',False):
        return self.original_read_cooperation_info(inspect_realworld=inspect_realworld)
    self.screenshot()
    if not board_visible(self):
        raise GameStuckError('New quest board is not confirmed before scanning')
    result=[]
    for n,button in enumerate(INVITES):
        self.screenshot()
        available=self.appear(button)
        already_shared=False
        completed=False
        identity=None
        if not available:
            box=(95+282*n,433,250,95)
            reader=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',
                           name=f'blackgold_card_check_{n+1}')
            identity=''.join(item.ocr_text for item in reader.detect_and_ocr(self.device.image)).replace(' ','')
            cooperation_text='自己击败' in identity or '好友击败' in identity or '邀请好友' in identity or '共享任务' in identity
            if not cooperation_text:
                continue
            if ('自己击败' in identity and '好友击败' in identity and self.appear(SHARED[n])):
                already_shared=True
                button=SHARED[n]
            else:
                claimbox=(140+282*n,330,160,110)
                claimreader=RuleOcr(roi=claimbox,area=claimbox,mode='Full',method='Default',keyword='',
                                    name=f'blackgold_claim_check_{n+1}')
                claimtext=''.join(x.ocr_text for x in claimreader.detect_and_ocr(self.device.image)).replace(' ','')
                if '自己击败' in identity and '好友击败' in identity and '领取' in claimtext:
                    already_shared=True
                    completed=True
                    button=None
                elif '自己击败' in identity and '好友击败' in identity and 'OASPlayer' in claimtext:
                    already_shared=True
                    button=SHARED[n]
                else:
                    self.device.save_screenshot(genre='findjade_unknown_invite',interval=1)
                    raise GameStuckError(f'Cooperation controls unrecognized in slot {n+1}; scan incomplete')
        reward=None
        for label,kind in [('JADE',T.Jade),('DOG_FOOD',T.Food),('CAT_FOOD',T.Food),('SUSHI',T.Sushi),('GOLD',T.Gold)]:
            old=getattr(A,f'I_WQ_COOPERATION_TYPE_{label}_1')
            marker=RuleImage(roi_front=(120+282*n,520,180,90),roi_back=(115+282*n,515,230,105),
                             method='Template matching',threshold=.8,file=old.file)
            if self.appear(marker):
                reward=(label,kind)
                break
        if reward is None:
            raise GameStuckError(f'Unknown black-gold cooperation reward in slot {n+1}')
        realworld=False
        if inspect_realworld:
            box=(95+282*n,433,250,95)
            identity_reader=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',
                                    name=f'blackgold_identity_{n+1}')
            if identity is None:
                identity=''.join(item.ocr_text for item in identity_reader.detect_and_ocr(self.device.image))
            if not identity:
                raise GameStuckError(f'Cannot identify cooperation card {n+1} before using scan cache')
            key=(n,reward[0],identity)
            if not hasattr(self,'black_gold_quest_kinds'):
                self.black_gold_quest_kinds={}
            if key not in self.black_gold_quest_kinds:
                self.black_gold_quest_kinds[key]=(self.cooperation_is_realworld(button,card_position=n)
                                                   if already_shared else self.cooperation_is_realworld(button))
            realworld=self.black_gold_quest_kinds[key]
        result.append(dict(type=T.RealWorld if realworld else reward[1],reward_type=reward[1],
                           reward_kind=reward[0],slot=n+1,inviteBtn=button,already_shared=already_shared,
                           completed=completed))
        self.cooperation_observer(result)
    if not result:
        words=''.join(item.ocr_text for item in CARD_TEXT.detect_and_ocr(self.device.image))
        if any(text in words for text in ('邀请好友','好友击败','自己击败','共享任务')):
            self.device.save_screenshot(genre='findjade_unknown_invite',interval=1)
            raise GameStuckError('Cooperation text is visible but invite controls are unrecognized; do not report an empty board')
    logger.info('New quest board scan: %s cooperation tasks',len(result))
    return result


def cooperation_is_realworld(self,button,card_position=None):
    if not getattr(self,'black_gold_skin',False):
        return self.original_cooperation_is_realworld(button)
    deadline=monotonic()+12
    clicked=False
    while monotonic()<deadline:
        self.screenshot()
        if self.appear(DETAIL_CLOSE):
            words=''.join(item.ocr_text for item in DETAIL_TEXT.detect_and_ocr(self.device.image)).replace(' ','')
            if '前往现世' in words or '现世妖怪' in words:
                realworld=True
            elif ('自己击败' in words and '好友击败' in words) or any(
                    self.appear(getattr(self,f'I_GOTO_{n}')) for n in range(1,5)):
                realworld=False
            else:
                continue
            self.close_cooperation_detail()
            return realworld
        if not clicked:
            if card_position is not None:
                self.device.click(220+282*card_position,230,control_name='blackgold_completed_quest_detail')
                clicked=True
            elif (confirmed_ocr_invite(self, button) if isinstance(button, RuleClick)
                  else self.appear(button)):
                x,y,w,h=button.roi_front
                self.device.click(x+w//2,y-65,control_name='blackgold_quest_detail')
                clicked=True
    raise GameStuckError('Cannot classify black-gold quest detail; no invitation sent')


def all_cooperation_invite(self,name_all=None):
    if not getattr(self,'black_gold_skin',False):
        return self.original_all_cooperation_invite(name_all)
    items=self.get_cooperation_info()  # FindJade excludes real-world quests here.
    for item in items:
        if item.get('already_shared'):
            logger.info('Skip invitation for already shared cooperation in slot %s',item['slot'])
            continue
        name=name_all or self.get_invite_vip_name(item['type'])
        if not name:
            continue
        current=self.get_cooperation_info()
        item=next((entry for entry in current if entry['slot']==item['slot'] and
                   entry['type']==item['type'] and entry['reward_kind']==item['reward_kind']),None)
        if item is None:
            raise GameStuckError('Cooperation board changed before inviting; preserve account')
        success=self.cooperation_invite(item['inviteBtn'],name)
        if success:
            item['send_confirmation']=self.last_invitation_confirmation
        if not success and getattr(self,'cooperation_recipient_unavailable',False):
            item['skip_reason']='大号已有协作，可邀请列表未显示：'+name
        self.cooperation_invite_result(item,name,success)
        if not success:
            if not getattr(self,'cooperation_recipient_unavailable',False):
                raise GameStuckError('Invitation could not be confirmed on new quest board')
            continue
        self.invite_success_callback(item['type'],name)
        if not self.trace_one(item['inviteBtn']):
            raise GameStuckError('Invitation sent but tracking not confirmed on new board')
        self.cooperation_sender_traced(item,name)
    return items


def wait_invitation_closed(self,timeout=8):
    """A pressed button disappearing for one frame is not a completed send."""
    deadline=monotonic()+timeout
    frames=0
    while monotonic()<deadline:
        self.screenshot()
        frames=frames+1 if board_visible(self) else 0
        if frames>=2:
            return True
    return False


def cooperation_invite(self,button,name):
    if not getattr(self,'black_gold_skin',False):
        return self.original_cooperation_invite(button,name)
    self.cooperation_recipient_unavailable=False
    self.last_invitation_confirmation=None
    if isinstance(button, RuleClick):
        deadline=monotonic()+12
        last_click=None
        opened=False
        while monotonic()<deadline:
            self.screenshot()
            if self.appear(self.I_WQ_INVITE_ENSURE):
                opened=True
                break
            if (last_click is None or monotonic()-last_click>=2.5) and confirmed_ocr_invite(self,button):
                self.device.click(*button.center,control_name=button.name)
                last_click=monotonic()
        if not opened:
            raise GameStuckError('Cannot confirm OCR invite control or open black-gold invitation list')
    elif not self.ui_click(button,stop=self.I_WQ_INVITE_ENSURE,interval=2.5,timeout=12):
        raise GameStuckError('Cannot open black-gold invitation list')
    name_seen=False
    selected=False
    for tab in range(2):
        if tab:
            self.device.click(315,120,control_name='blackgold_cross_server_friends')
        deadline=monotonic()+4
        clicked=False
        target=None
        while monotonic()<deadline:
            self.screenshot()
            if not self.appear(self.I_WQ_INVITE_ENSURE):
                continue
            if clicked:
                if self.appear(self.I_WQ_INVITE_SELECTED):
                    sx,sy,sw,sh=self.I_WQ_INVITE_SELECTED.roi_front
                    if abs(sy+sh//2-target[1])<55 and abs(sx+sw//2-target[0])<210:
                        selected=True
                        break
                continue
            for x in (240,520):
                reader=RuleOcr(roi=(x,185,190,340),area=(x,185,190,340),mode='Full',
                               method='Default',keyword=name,name='blackgold_exact_recipient')
                for result in reader.detect_and_ocr(self.device.image):
                    if result.ocr_text.replace(' ','')!=name.replace(' ',''):
                        continue
                    box=result.box
                    target=(int(x+(box[:,0].min()+box[:,0].max())/2),
                            int(185+(box[:,1].min()+box[:,1].max())/2))
                    name_seen=True
                    self.device.click(*target,control_name='blackgold_select_'+name)
                    clicked=True
                    break
                if clicked:
                    break
        if selected or name_seen:
            break
    if not selected:
        # A visible name without a confirmed tick is a selection failure, not excess.
        self.cooperation_recipient_unavailable=not name_seen
        self.screenshot()
        if self.appear(self.I_WQ_INVITE_CANCEL):
            x,y,w,h=self.I_WQ_INVITE_CANCEL.roi_front
            self.device.click(x+w//2,y+h//2,control_name='blackgold_cancel_invitation')
            if not wait_invitation_closed(self):
                raise GameStuckError('Invitation cancel did not return to quest board')
        else:
            raise GameStuckError('Invitation list disappeared before recipient selection')
        return False
    # Recheck both controls immediately before the single central submit click.
    self.screenshot()
    if not self.appear(self.I_WQ_INVITE_SELECTED) or not self.appear(self.I_WQ_INVITE_ENSURE):
        raise GameStuckError('Recipient selection changed before invitation submission')
    x,y,w,h=self.I_WQ_INVITE_ENSURE.roi_front
    point=(x+w//2,y+h//2)
    logger.info('FindJade sending invitation to %s at verified button center %s',name,point)
    self.device.click(*point,control_name='blackgold_submit_invitation')
    if not wait_invitation_closed(self):
        raise GameStuckError('Invitation submission did not return to a stable quest board; not recorded as sent')
    self.last_invitation_confirmation='exact_recipient_selected_center_clicked_board_stable'
    logger.info('FindJade invitation submission confirmed for %s; main-account acceptance remains unconfirmed',name)
    return True
