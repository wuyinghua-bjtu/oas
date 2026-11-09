"""Read stable card text with per-slot fallback for the current bounty skin."""
from tasks.FindJade.black_gold import *
from module.atom.click import RuleClick
from time import sleep

def read_cooperation_info(self,inspect_realworld=False):
    if not getattr(self,'black_gold_skin',False):
        return self.original_read_cooperation_info(inspect_realworld=inspect_realworld)
    self.screenshot()
    if not board_visible(self):
        raise GameStuckError('New quest board is not confirmed before scanning')
    sleep(1)
    self.screenshot()
    board_words=CARD_TEXT.detect_and_ocr(self.device.image)
    result=[]
    for n,button in enumerate(INVITES):
        self.screenshot()
        available=self.appear(button)
        already_shared=False
        completed=False
        identity=None
        if not available:
            box=(90+282*n,390,265,145)
            reader=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',
                           name=f'blackgold_card_check_{n+1}')
            identity=''.join(item.ocr_text for item in reader.detect_and_ocr(self.device.image)).replace(' ','')
            if not identity:
                identity=''.join(row.ocr_text for row in board_words if 90+282*n <= 85+sum(float(p[0]) for p in row.box)/len(row.box) < 355+282*n).replace(' ','')
            cooperation_text='自己击败' in identity or '好友击败' in identity or '邀请好友' in identity or '共享任务' in identity
            if not cooperation_text:
                continue
            if '邀请好友' in identity:
                button=RuleClick(roi_front=(170+282*n,407,85,20),roi_back=(90+282*n,390,265,60),name=f'confirmed_invite_{n+1}')
            elif ('自己击败' in identity and '好友击败' in identity and self.appear(SHARED[n])):
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
                elif '自己击败' in identity and '好友击败' in identity and any(
                        name in claimtext or name in identity for name in ('OASPlayer','OASMain')):
                    already_shared=True
                    button=SHARED[n]
                else:
                    self.device.save_screenshot(genre='findjade_unknown_invite',interval=1)
                    raise GameStuckError(f'Cooperation controls unrecognized in slot {n+1}; scan incomplete')
        reward=None
        jade_marker=RuleImage(roi_front=(120+282*n,520,180,90),roi_back=(115+282*n,515,230,105),
                              method='Template matching',threshold=.88,
                              file='./tasks/FindJade/res/blackgold_reward_jade.png')
        if self.appear(jade_marker):
            reward=('JADE',T.Jade)
        for label,kind in [('JADE',T.Jade),('DOG_FOOD',T.Food),('CAT_FOOD',T.Food),('SUSHI',T.Sushi),('GOLD',T.Gold)]:
            if reward is not None:
                break
            old=getattr(A,f'I_WQ_COOPERATION_TYPE_{label}_1')
            marker=RuleImage(roi_front=(120+282*n,520,180,90),roi_back=(115+282*n,515,230,105),
                             method='Template matching',threshold=.8,file=old.file)
            if self.appear(marker):
                reward=(label,kind)
                break
        realworld=False
        # An unrecognized reward must not stop a positively identified
        # real-world quest from being recorded. Classify it first; unknown
        # rewards on ordinary cooperation remain a hard stop.
        if inspect_realworld or reward is None:
            box=(90+282*n,390,265,145)
            identity_reader=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',
                                    name=f'blackgold_identity_{n+1}')
            if identity is None:
                identity=''.join(item.ocr_text for item in identity_reader.detect_and_ocr(self.device.image))
            if not identity:
                raise GameStuckError(f'Cannot identify cooperation card {n+1} before using scan cache')
            key=(n,reward[0] if reward else 'UNKNOWN',identity)
            if not hasattr(self,'black_gold_quest_kinds'):
                self.black_gold_quest_kinds={}
            if key not in self.black_gold_quest_kinds:
                self.black_gold_quest_kinds[key]=(self.cooperation_is_realworld(button,card_position=n)
                                                   if already_shared else self.cooperation_is_realworld(button))
            realworld=self.black_gold_quest_kinds[key]
        if reward is None:
            if not realworld:
                self.device.save_screenshot(genre='findjade_unknown_reward',interval=1)
                raise GameStuckError(f'Unknown black-gold cooperation reward in slot {n+1}')
            reward=('UNKNOWN',None)
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

