import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from tasks.GameUi.assets import GameUiAssets


def capture(source, destination):
    image = Image.open(source).convert('RGB').resize((1280, 720))
    frame = np.array(image)
    records = []
    for name in ('SHIKIGAMI_RECORDS', 'ONMYODO', 'FRIENDS', 'DAILY', 'MALL',
                 'GUILD', 'TEAM', 'COLLECTION', 'TRAVEL'):
        rule = getattr(GameUiAssets, 'I_MAIN_GOTO_' + name)
        if not rule.match(frame):
            raise RuntimeError('Cannot locate menu item: ' + name)
        records.append(('main_goto_' + name.lower(), list(rule.roi_front),
                        list(rule.roi_back), max(0.8, rule.threshold)))
    records.append(('profile_badge_current', [101, 12, 27, 34], [95, 5, 45, 55], 0.85))
    paths = [destination / (name + '.png') for name, *_ in records]
    paths.append(destination / 'image.json')
    if any(path.exists() for path in paths):
        raise FileExistsError('Template capture never overwrites existing assets')
    destination.mkdir(parents=True, exist_ok=True)
    metadata = []
    for name, front, back, threshold in records:
        left, top, width, height = front
        image_name = name + '.png'
        image.crop((left, top, left + width, top + height)).save(destination / image_name)
        metadata.append(dict(itemName=name, imageName=image_name, roiFront=front,
                             roiBack=back, method='Template matching', threshold=threshold))
    with (destination / 'image.json').open('x', encoding='utf-8') as output:
        json.dump(metadata, output, ensure_ascii=False, indent=2)
    print('Recorded', len(metadata), 'templates:', destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    arguments = parser.parse_args()
    capture(arguments.source, arguments.destination)
