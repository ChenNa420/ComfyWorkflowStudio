from __future__ import annotations

from urllib.parse import urlsplit

SENSITIVE_KEYS = ('token', 'authorization', 'cookie', 'secret', 'signature', 'credential')
REFERENCE_KEYS = ('attachment', 'asset', 'resource', 'file', 'url', 'uri', 'ref', 'reference')


def safe_url_scheme(value: object) -> str | None:
    if not isinstance(value, str) or ':' not in value:
        return None
    scheme = urlsplit(value).scheme.lower()
    return scheme if scheme in {'http', 'https', 'blob', 'data', 'file'} else 'other'


def sanitize_probe_metadata(image: object) -> dict:
    value_type = type(image).__name__
    if isinstance(image, str):
        scheme = safe_url_scheme(image)
        return {'argumentType': 'string', 'constructor': 'str', 'objectKeys': [], 'mime': None,
                'name': None, 'size': None, 'urlScheme': scheme, 'referenceType': 'url' if scheme else None}
    if not isinstance(image, dict):
        return {'argumentType': value_type, 'constructor': value_type, 'objectKeys': [], 'mime': None,
                'name': None, 'size': None, 'urlScheme': None, 'referenceType': None}
    safe_keys = sorted(key for key in image if not any(secret in key.lower() for secret in SENSITIVE_KEYS))[:20]
    mime = next((image.get(key) for key in ('type', 'mime', 'mimeType', 'contentType') if isinstance(image.get(key), str)), None)
    name = image.get('name') if isinstance(image.get('name'), str) else None
    size = image.get('size') if isinstance(image.get('size'), (int, float)) else None
    url_value = next((image.get(key) for key in ('url', 'uri', 'href') if isinstance(image.get(key), str)), None)
    ref_type = next((key for key in REFERENCE_KEYS if any(key in item.lower() for item in safe_keys)), None)
    return {'argumentType': 'object', 'constructor': 'dict', 'objectKeys': safe_keys,
            'mime': mime[:100] if mime else None, 'name': name[:200] if name else None, 'size': size,
            'urlScheme': safe_url_scheme(url_value), 'referenceType': ref_type}


def classify_probe(metadata: dict, binary_accessible: bool = False) -> str:
    constructor = str(metadata.get('constructor') or '').lower()
    reference = str(metadata.get('referenceType') or '').lower()
    if binary_accessible and constructor in {'file', 'blob'}:
        return 'DIRECT_FILE_SUPPORTED'
    if 'attachment' in reference:
        return 'ATTACHMENT_REFERENCE_SUPPORTED'
    if 'resource' in reference or 'asset' in reference:
        return 'RESOURCE_REFERENCE_SUPPORTED'
    if metadata.get('urlScheme') in {'http', 'https', 'blob'}:
        return 'RESOURCE_URL_SUPPORTED'
    return 'IMAGE_NOT_TRANSFERABLE'
