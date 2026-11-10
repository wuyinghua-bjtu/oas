"""Narrow OCR correction for the configured account cards."""
from module.atom.ocr import RuleOcr
from module.logger import logger


class MingCharacterList(RuleOcr):
    def __init__(self, expected):
        box=(418,131,641,481)
        super().__init__(roi=box,area=box,mode='Full',method='Default',keyword='',
                         name='switch_ming_character_list')
        self.expected=expected

    def detect_and_ocr(self,image,logDisplay=True):
        rows=super().detect_and_ocr(image,logDisplay=logDisplay)
        servers=[r for r in rows if r.ocr_text.replace(' ','')=='砂狐乐园']
        for row in rows:
            text=row.ocr_text.lstrip('1234567890 ([<>])【】（）《》').replace(' ','')
            if text not in (self.expected[1:], '买'+self.expected[1:], '宾'+self.expected[1:]):
                continue
            x,y=row.box[0]
            if any(abs(float(x-server.box[0][0]))<100 and
                   50<float(y-server.box[0][1])<105 for server in servers):
                row.ocr_text=self.expected
                logger.info('Matched OCR variant to %s using the same 砂狐乐园 card',self.expected)
        return rows
