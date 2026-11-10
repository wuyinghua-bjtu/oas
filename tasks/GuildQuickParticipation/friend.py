"""Verified friend actions, limited to the named main account."""
from module.config.local_values import local_text
from time import monotonic
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.exception import GameStuckError
from tasks.GameUi.page import page_friends

TARGET=local_text('LOCAL_SUPPORT_')
ROOT='./tasks/GuildQuickParticipation/res/'


def marker(name, front, back):
    return RuleImage(roi_front=front,roi_back=back,method='Template matching',
                     threshold=.84,file=ROOT+name+'.png')


def name_location(image, box, name=TARGET):
    reader=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',name='guild_main_friend')
    matches=[r for r in reader.detect_and_ocr(image) if r.ocr_text.replace(' ','')==name]
    if len(matches)!=1:
        return None
    b=matches[0].box
    return (int(box[0]+(b[:,0].min()+b[:,0].max())/2),
            int(box[1]+(b[:,1].min()+b[:,1].max())/2))


def name_candidates(image, box, name=TARGET):
    """All rows that read back as the bare target nickname, top to bottom."""
    reader=RuleOcr(roi=box,area=box,mode='Full',method='Default',keyword='',name='guild_main_friend')
    out=[]
    for r in reader.detect_and_ocr(image):
        if r.ocr_text.replace(' ','')==name:
            b=r.box
            out.append((int(box[0]+(b[:,0].min()+b[:,0].max())/2),
                        int(box[1]+(b[:,1].min()+b[:,1].max())/2)))
    out.sort(key=lambda p:p[1])
    return out


def perform_friend_actions(task, timeout=25):
    """Like and send friendship only to the confirmed main account.

    Unknown screens or an absent name stop the task. The caller records the
    returned individual states and handles account switching.
    """
    task.ui_get_current_page()
    task.ui_goto(page_friends)
    # The friends page can be visible before its list has finished loading.
    # Wait for the exact target; do not select a different visible friend.
    notice=marker('friend_bond_notice',(466,99,344,67),(450,85,380,95))
    deadline=monotonic()+timeout
    candidates=[]
    expanded=False
    while monotonic()<deadline:
        task.screenshot()
        # The bond-upgrade banner covers the list and clips row suffixes, so
        # clear it before reading any nickname.
        if task.appear(notice):
            task.device.click(1149,91,control_name='guild_close_friend_bond_notice')
            continue
        candidates=name_candidates(task.device.image,(205,190,180,370))
        if candidates:
            break
        # A collapsed same-server group leaves only cross-server friends
        # visible. Expand the independently recognized group header once;
        # still require the exact main-account name before selecting anyone.
        if not expanded:
            header=RuleOcr(roi=(240,150,165,45),area=(240,150,165,45),
                           mode='Full',method='Default',keyword='',name='guild_friend_group')
            texts=[r.ocr_text.replace(' ','') for r in header.detect_and_ocr(task.device.image)]
            if any(text.startswith('好友:') or text.startswith('好友：') for text in texts):
                task.device.click(470,174,control_name='guild_expand_same_server_friends')
                expanded=True
    if not candidates:
        raise GameStuckError('Main account not uniquely visible in friends list')
    # A portrait or the bond banner can clip the numeric suffix, so several
    # rows may read back as the bare nickname. Open each candidate and let the
    # friend panel prove the identity before liking anybody.
    panel_box=(610,92,145,42)
    confirmed=False
    selected_center=None
    for center in candidates[:4]:
        task.device.click(*center,control_name='guild_select_main_friend')
        deadline=monotonic()+8
        while monotonic()<deadline:
            task.screenshot()
            if task.appear(notice):
                task.device.click(1149,91,control_name='guild_close_friend_bond_notice')
                continue
            if name_location(task.device.image,panel_box) is not None:
                confirmed=True
                selected_center=center
                break
        if confirmed:
            break
    if not confirmed:
        raise GameStuckError('Friend panel did not confirm target name')
    notices_closed=0
    next_notice=0
    ready=marker('like_ready',(617,141,33,29),(610,135,48,42))
    done=marker('like_done',(617,141,33,29),(610,135,48,42))
    if task.appear(done):
        like='已点赞'
    elif task.appear(ready):
        task.device.click(630,155,control_name='guild_like_main_friend')
        deadline=monotonic()+timeout
        while monotonic()<deadline:
            task.screenshot()
            if task.appear(notice):
                if notices_closed<4 and monotonic()>=next_notice:
                    task.device.click(1149,91,control_name='guild_close_friend_bond_notice')
                    notices_closed+=1
                    next_notice=monotonic()+1
                continue
            if task.appear(done):
                like='点赞成功'
                break
        else:
            raise GameStuckError('Like confirmation not observed')
    else:
        raise GameStuckError('Friend like button state is unrecognized')
    # The bottom selector reveals gift icons in each friend row.
    task.device.click(160,665,control_name='guild_friendship_points_tab')
    deadline=monotonic()+timeout
    received=False
    while monotonic()<deadline:
        task.screenshot()
        y=selected_center[1]-12
        send=marker('friend_send',(429,y,65,64),(419,y-10,85,84))
        sent=marker('friend_sent',(429,y,65,64),(419,y-10,85,84))
        receive=marker('friend_receive',(429,y,65,64),(419,y-10,85,84))
        if task.appear(sent):
            return {'like':like,'friendship':'已赠送'}
        if not received and task.appear(receive):
            x,top,w,h=receive.roi_front
            task.device.click(x+w//2,top+h//2,control_name='guild_receive_friendship_main')
            received=True
            continue
        if task.appear(send):
            x,top,w,h=send.roi_front
            task.device.click(x+w//2,top+h//2,control_name='guild_send_friendship_main')
            while monotonic()<deadline:
                task.screenshot()
                if task.appear(sent):
                    return {'like':like,'friendship':'赠送成功'}
            raise GameStuckError('Friendship gift confirmation not observed')
    raise GameStuckError('Friendship gift control unrecognized')
