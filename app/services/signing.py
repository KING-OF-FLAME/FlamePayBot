import hashlib
import json
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize(value[k]) for k in sorted(value.keys()) if value[k] not in (None, '', [])}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def flatten_sign_data(data: dict[str, Any], ignore_keys: set[str] | None = None) -> str:
    ignored = set(ignore_keys or set()) | {'sign'}
    normalized = _normalize({k: v for k, v in data.items() if k not in ignored and v not in (None, '', [])})
    parts = []
    for k in sorted(normalized.keys()):
        v = normalized[k]
        if isinstance(v, (dict, list)):
            v = json.dumps(v, separators=(',', ':'), ensure_ascii=False)
        parts.append(f'{k}={v}')
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
