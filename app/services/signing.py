import hashlib
import json
from typing import Any


_EMPTY_VALUES = (None, '')


def _is_empty(value: Any) -> bool:
    if value in _EMPTY_VALUES:
        return True
    if isinstance(value, (dict, list, tuple, set)) and len(value) == 0:
        return True
    return False


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value.keys()):
            child = _normalize(value[key])
            if _is_empty(child):
                continue
            normalized[key] = child
        return normalized
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def flatten_sign_data(data: dict[str, Any], ignore_keys: set[str] | None = None) -> str:
    ignored = set(ignore_keys or set()) | {'sign'}
    normalized = _normalize({k: v for k, v in data.items() if k not in ignored and not _is_empty(v)})
    parts = []
    for key in sorted(normalized.keys()):
        value = normalized[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, separators=(',', ':'), ensure_ascii=False)
        parts.append(f'{key}={value}')
    return '&'.join(parts)


def make_sign(data: dict[str, Any], key: str, sign_type: str, ignore_keys: set[str] | None = None) -> str:
    src = f"{flatten_sign_data(data, ignore_keys=ignore_keys)}&key={key}"
    sign_type = sign_type.upper()
    if sign_type == 'MD5':
        digest = hashlib.md5(src.encode('utf-8')).hexdigest()
    elif sign_type == 'SHA1':
        digest = hashlib.sha1(src.encode('utf-8')).hexdigest()
    elif sign_type == 'SHA256':
        digest = hashlib.sha256(src.encode('utf-8')).hexdigest()
    else:
        raise ValueError(f'Unsupported sign type: {sign_type}')
    return digest.upper()


def verify_sign(data: dict[str, Any], key: str, sign_type: str) -> bool:
    incoming = str(data.get('sign', '')).upper()
    if not incoming:
        return False
    calculated = make_sign(data, key, sign_type)
    return calculated == incoming
