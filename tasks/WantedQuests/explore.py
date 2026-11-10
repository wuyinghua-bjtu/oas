from cached_property import cached_property

from module.atom.animate import RuleAnimate
from module.atom.image import RuleImage
from module.base.timer import Timer
from module.logger import logger
from tasks.Exploration.base import BaseExploration, Scene
from tasks.Exploration.version import HighLight


class ExploreWantedBoss(Exception):
    # 出现一种情况，要求的怪是仅仅最后的Boss，其他小怪不是
    pass


class WQExplore(BaseExploration, HighLight):
    _cnt_exploration: int = 0
    I_WQ_EXPLORE_SWORDS = RuleImage(roi_front=(1000,248,37,36), roi_back=(100,175,1170,375),
        threshold=0.9, method='Template matching', file='./tasks/WantedQuests/wq/wq_explore_swords.png')

    @cached_property
    def _match_end(self):
        return RuleAnimate(self.I_SWIPE_END)

    def explore(self, goto: RuleImage, num: int):
        logger.info(f'Start exploring with number: {num}')
        explore_init = False
        explore_only_boss: bool = True
        _cnt_exploration = 0
        search_fail_cnt = 0
        empty_sweeps = 0
        search_fail_timer = Timer(3.2)  # 这里设置的时间一定要大于S_SWIPE_BACKGROUND_RIGHT滑动的时间
        # https://github.com/runhey/OnmyojiAutoScript/pull/1697 云景阆苑 皮肤
        from tasks.Component.Costume.config import MainType
        if self.config.model.global_game.costume_config.costume_main_type == MainType.COSTUME_MAIN_13:
            self.TEMPLATE_GIF.match = self.TEMPLATE_GIF.match_with_multi_scale
            logger.info("Costume '云景阆苑' detected, enable multi-scale matching for highlight")
        else:
            self.TEMPLATE_GIF.match = self.TEMPLATE_GIF.match_origin
        while 1:
            self.screenshot()
            if self.appear(self.I_UI_BACK_YELLOW) and self.appear(self.I_E_EXPLORATION_CLICK):
                break
            if self.appear_then_click(goto, interval=2):
                continue

        while 1:
            scene = self.get_current_scene(reuse_screenshot=False)
            # 进入探索
            if scene == Scene.ENTRANCE:
                if _cnt_exploration >= num:
                    logger.info('Execution exploration end')
                    # --退出到探索大世界--
                    self.ui_click(self.I_UI_BACK_YELLOW, stop=self.I_CHECK_EXPLORATION, interval=4)
                    if explore_only_boss:
                        raise ExploreWantedBoss
                    break
                if hasattr(self, 'support_account'):
                    self.device.save_screenshot(genre='findjade_explore_entrance', interval=0)
                self.ui_click(self.I_E_EXPLORATION_CLICK, stop=self.I_E_SETTINGS_BUTTON)
                continue
            # 探索大世界
            elif scene == Scene.WORLD:
                self.wait_until_stable(
                    self.I_CHECK_EXPLORATION,
                    timer=Timer(limit=0.5, count=2),
                    timeout=Timer(2, count=10)
                )
                curr_scene = self.get_current_scene(reuse_screenshot=False)
                if curr_scene == Scene.WORLD and _cnt_exploration >= num:
                    logger.info('All Done')
                    break
                continue
            # 探索里面
            elif scene == Scene.MAIN:
                # if not explore_init:
                #     count = 0
                #     while count < 5:
                #         if self.appear(self.I_E_AUTO_ROTATE_ON):
                #             break
                #         if self.appear(self.I_E_AUTO_ROTATE_OFF, interval=1.5):
                #             self.click(self.I_E_AUTO_ROTATE_OFF)
                #             count += 1
                #     explore_init = True
                #     continue
                if hasattr(self, 'support_account') and not explore_init:
                    self.device.save_screenshot(genre='findjade_explore_map', interval=0)
                    explore_init = True
                # 小纸人
                if self.appear(self.I_BATTLE_REWARD):
                    if self.ui_get_reward(self.I_BATTLE_REWARD):
                        continue
                # Only the bounty highlight authorizes a fight. A generic
                # boss/sword icon proves challengeability, not target identity.
                if self.appear(self.TEMPLATE_GIF) and self.fire(self.TEMPLATE_GIF):
                    explore_only_boss = False
                    empty_sweeps = 0
                    logger.info(f'Fight highlighted bounty target, minions cnt {self.minions_cnt}')
                    continue
                # 向后拉,寻找怪
                if search_fail_timer.reached():
                    search_fail_timer.reset()
                    if self._match_end.stable(self.device.image, refresh_after_stable=True):
                        empty_sweeps += 1
                        logger.warning('未识别到悬赏高亮目标，退出重打进图，连续第 %s 次', empty_sweeps)
                        self.device.save_screenshot(genre='findjade_highlight_missing', interval=0)
                        if empty_sweeps >= 3:
                            self.quit_explore()
                            raise ExploreWantedBoss
                        _cnt_exploration += 1
                        self.quit_explore()
                        continue
                    if self.swipe(self.S_SWIPE_BACKGROUND_RIGHT, interval=3):
                        continue
                if not search_fail_timer.started():
                    search_fail_timer.start()
            elif scene == Scene.BATTLE_PREPARE:
                self.ui_click_until_disappear(self.I_PREPARE_HIGHLIGHT, interval=0.5)
            elif scene == Scene.UNKNOWN:
                continue


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    from tasks.WantedQuests.assets import WantedQuestsAssets

    config = Config('oas1')
    device = Device(config)
    t = WQExplore(config, device)
    t.explore(goto=WantedQuestsAssets.I_GOTO_1, num=2)
