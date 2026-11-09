from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.base_task import BaseTask
from module.logger import logger
from module.exception import GameStuckError


class ExitGame(BaseTask, SwitchAccountAssets):

    def exitGame(self):
        logger.info("start game exit")
        # 打开该页面比较慢 如果interval短 将发生异常
        # The SDK welcome banner can cover the old top-of-profile marker.
        # Confirm the user-center button that the next step actually needs.
        if not self.ui_click(self.C_SA_EG_PROFILE_PHOTO, self.I_SA_USER_CENTER, 3, timeout=12):
            raise GameStuckError('Cannot open account profile for switching')
        if not self.ui_click(self.I_SA_USER_CENTER, self.I_SA_SWITCH_ACCOUNT_BTN, 6, timeout=15):
            raise GameStuckError('Cannot open account user center for switching')
        self.ui_click_until_disappear(self.I_SA_SWITCH_ACCOUNT_BTN, 3)
