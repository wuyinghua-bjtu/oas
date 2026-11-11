import json
from pathlib import Path

from module.atom.image import RuleImage


TEMPLATE_DIRECTORY = Path(__file__).with_name('courtyard_current')


def load_templates():
    if not (TEMPLATE_DIRECTORY / 'image.json').is_file():
        return {}
    records = json.loads((TEMPLATE_DIRECTORY / 'image.json').read_text(encoding='utf-8'))
    return {
        record['itemName']: RuleImage(
            tuple(record['roiFront']), tuple(record['roiBack']),
            record['method'], record['threshold'],
            str(TEMPLATE_DIRECTORY / record['imageName']),
        )
        for record in records
        if (TEMPLATE_DIRECTORY / record['imageName']).is_file()
    }


class CourtyardTemplateAssets:
    templates = None

    @classmethod
    def get_templates(cls):
        if cls.templates is None:
            cls.templates = load_templates()
        return cls.templates

    @classmethod
    def menu_visible(cls, image):
        if image is None or image.shape[:2] != (720, 1280):
            return False
        matches = 0
        for name, rule in cls.get_templates().items():
            if name.startswith('main_goto_') and rule.match(image):
                matches += 1
                if matches >= 3:
                    return True
        return False
