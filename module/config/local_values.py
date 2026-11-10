import json
import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _values():
    path = Path(__file__).resolve().parents[2] / 'config' / 'local_values.json'
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or any(not isinstance(value, str) for value in data.values()):
        raise ValueError('config/local_values.json must contain string values')
    return data


def local_text(public_text):
    values = _values()
    if not values:
        return public_text
    pattern = '|'.join(re.escape(key) for key in sorted(values, key=len, reverse=True) if key)
    if not pattern:
        return public_text
    return re.sub(pattern, lambda match: values[match.group(0)], public_text)
