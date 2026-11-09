from adbutils import device

from module.config.config import Config
from module.device.device import Device
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.Component.SwitchAccount.exit_game import ExitGame
from tasks.Component.SwitchAccount.login_account import LoginAccount
from tasks.Component.SwitchAccount.switch_account_config import AccountInfo
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_login
from tasks.base_task import BaseTask
from tasks.Restart.login import LoginHandler

from module.logger import logger
from module.atom.ocr import RuleOcr
from module.exception import RequestHumanTakeover, GameStuckError, GameTooManyClickError
import re
import time


class SwitchAccount(LoginAccount, ExitGame, GameUi, SwitchAccountAssets):

    @staticmethod
    def verification_name(text):
        return re.sub(r'[\s#·•]', '', text or '').rstrip('。.,，')

    def __init__(self, config: Config, device: Device, to: AccountInfo, frm: AccountInfo = None):
        """

        @param config:
        @type config:
        @param device:
        @type device:
        @param to: 要登录的账号信息
        @type to:
        @param frm: 上一个账号信息 ,避免关键字from
        @type frm:
        """
        super().__init__(config, device)
        self.to_account_info = to
        self.from_account_info = frm
        if to.svr == '砂狐乐园' and to.character.startswith('冥界画师'):
            from tasks.Component.SwitchAccount.character_list import MingCharacterList
            self.O_SA_SELECT_SVR_CHARACTER_LIST=MingCharacterList(to.character)

    def switchAccount(self, skip_harvest=False):
        logger.info("start switchAccount %s-%s", self.to_account_info.character, self.to_account_info.svr)
        # 判断所处界面
        curPage = self.ui_get_current_page(skip_first_screenshot=False)

        if curPage != page_login and curPage != page_main:
            self.ui_goto(page_main)
            curPage = self.ui_get_current_page()
        if curPage == page_main:
            self.exitGame()

        # 网络较差时，登录页的服务器/角色列表会长时间加载不出来。
        # 这种情况不需要重启游戏，原样再执行一遍切号动作即可。
        login_ok = False
        for attempt in range(3):
            if attempt:
                logger.warning('Login page did not load; re-run the account switch action (%s/3)', attempt + 1)
                self.device.click_record_clear()
                self.device.stuck_record_clear()
                time.sleep(5)
            else:
                # A stale watchdog from an earlier page must not abort the retry.
                self.device.stuck_record_clear()
            try:
                login_ok = self.login(self.to_account_info)
            except (GameStuckError, GameTooManyClickError) as error:
                logger.warning('Login attempt failed: %s; re-run the account switch action', error)
                login_ok = False
            if login_ok:
                break
        if not login_ok:
            return False
        logger.info("%s login suc", self.to_account_info.character)
        # 处理位于登录界面各种奇葩弹窗
        login_handler = LoginHandler(config=self.config, device=self.device)
        login_handler.set_specific_usr(self.to_account_info.svr)
        if skip_harvest:
            # Account enumeration must not collect gifts or run optional daily
            # actions before the support account's identity has been verified.
            login_handler._app_handle_login()
        else:
            login_handler.app_handle_login()

        # Keep the nickname and its numeric suffix, excluding the decorative
        # badge on the right that some profile frames read as an extra "人".
        name_ocr = RuleOcr(roi=(125,25,150,32), area=(125,25,150,32),
                           mode='Single', method='Default', keyword='', name='switch_character_verify')
        observed = ''
        for _ in range(3):
            self.screenshot()
            observed = self.verification_name(name_ocr.ocr(self.device.image))
            if observed == self.verification_name(self.to_account_info.character):
                logger.info('Verified current character: %s', self.to_account_info.character)
                return True
        # The courtyard font can read 冥 as 买. Require the exact remaining
        # nickname and a separately matched observed 冥 glyph in two frames.
        expected=self.verification_name(self.to_account_info.character)
        if expected.startswith('冥界画师') and observed == '买'+expected[1:]:
            from module.atom.image import RuleImage
            glyph=RuleImage(roi_front=(130,33,21,22),roi_back=(125,28,31,32),
                            method='Template matching',threshold=.90,
                            file='./tasks/Component/SwitchAccount/res/sa_ming_character.png')
            verified=0
            for _ in range(2):
                self.screenshot()
                if not self.appear(glyph):
                    break
                verified+=1
            if verified==2:
                logger.info('Verified character using observed 冥 glyph and exact remaining nickname: %s', expected)
                return True
        raise RequestHumanTakeover(f'Character verification failed: expected {self.to_account_info.character}, observed {observed}')


if __name__ == '__main__':
    config = Config('oas1')
    device=Device()
    toAccount=AccountInfo(account="example@example.invalid", account_alias="emailO#emailo", apple_or_android=True, character="粘贴", svr="立秋夕烛")
    sa=SwitchAccount(config,device,toAccount)
    sa.switchAccount()
