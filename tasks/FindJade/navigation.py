"""Stable server selector for support-account enumeration."""
from module.atom.ocr import RuleOcr
from module.exception import GameStuckError


class SupportServerSwitch(RuleOcr):
    def __init__(self):
        box=(710,485,105,80)
        super().__init__(roi=box,area=box,mode='Full',method='Default',keyword='切换',
                         name='support_server_switch')
        self.clicks=0

    def coord(self):
        if self.clicks>=6:
            raise GameStuckError('Server selector did not open after six confirmed attempts')
        self.clicks+=1
        x,y,w,h=self.area
        if w<=0 or h<=0:
            raise GameStuckError('Server selector text location is unconfirmed')
        return 640,int(y+h/2)
