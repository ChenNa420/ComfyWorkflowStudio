from __future__ import annotations

import base64
import json
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from backend.ai.schema_prompt import schema_instruction, SCHEMAS
from backend.db import ROOT

_PROBE_STATE = {'reachable': False, 'visionVerified': False, 'structuredOutputVerified': False, 'lastProbeAt': None}
SEMANTIC_RULES = '''This is a comic understanding task, not free story writing.
1. Only report visually or textually supported facts.
2. Do not guess names; use unknown when the name is not visible.
3. Unknown is better than hallucination.
4. Preserve page evidence for every supported fact.
5. Speaker must remain null if uncertain.
6. Separate visible facts from inferred relationships.
7. Track the same character across pages cautiously and mark uncertain identity for review.
8. Never invent missing dialogue.
9. Page numbers must reference supplied pages only.
10. Confidence must reflect uncertainty.
Do not rewrite the plot, add dialogue, create an ending, or educationally adapt content.'''


def safe_base_url(value: str) -> str:
    try:
        part = urlsplit(value)
        host = part.hostname or ""
        port = f":{part.port}" if part.port else ""
        return urlunsplit((part.scheme, host + port, part.path.rstrip('/'), '', ''))
    except ValueError:
        return ""


def parse_json_response(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith('```'):
        lines = value.splitlines()
        if lines and lines[0].strip().lower() in {'```', '```json'}:
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        value = '\n'.join(lines).strip()
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError('AI_RESPONSE_INVALID')
    return parsed


class OpenAICompatibleComicProvider:
    name = 'openai_compatible'
    enabled = True

    def __init__(self) -> None:
        self.base_url = os.getenv('COMIC_AI_BASE_URL', '').strip().rstrip('/')
        self.model = os.getenv('COMIC_AI_MODEL', '').strip()
        self.api_key = os.getenv('COMIC_AI_API_KEY', '').strip()
        self.timeout = float(os.getenv('COMIC_AI_TIMEOUT', '90'))
        self.allow_remote = os.getenv('COMIC_AI_ALLOW_REMOTE', 'false').strip().lower() == 'true'
        self.structured_output = os.getenv('COMIC_AI_STRUCTURED_OUTPUT', 'json_object').strip().lower()
        self.max_retries = min(1, max(0, int(os.getenv('COMIC_AI_MAX_RETRIES', '0'))))
        self.debug = os.getenv('COMIC_AI_DEBUG', 'false').strip().lower() == 'true'

    def _is_local(self) -> bool:
        return (urlsplit(self.base_url).hostname or '').lower() in {'localhost', '127.0.0.1', '::1'}

    def get_status(self) -> dict[str, Any]:
        endpoint_allowed = self._is_local() or self.allow_remote
        configured = bool(self.base_url and self.model and endpoint_allowed)
        return {'provider': self.name, 'enabled': True, 'configured': configured,
                'model': self.model or None, 'baseUrlSafe': safe_base_url(self.base_url),
                'supportsVision': True, 'remoteAllowed': self.allow_remote, 'isLocalEndpoint': self._is_local(), **_PROBE_STATE,
                'reason': None if configured else ('Remote endpoint requires COMIC_AI_ALLOW_REMOTE=true' if self.base_url and self.model else 'COMIC_AI_BASE_URL and COMIC_AI_MODEL are required')}

    def _debug_response(self, purpose: str, value: dict[str, Any]) -> None:
        if not self.debug: return
        root = (ROOT / 'storage' / 'comic-analysis' / 'debug').resolve(); root.mkdir(parents=True, exist_ok=True)
        safe = json.loads(json.dumps(value))
        def redact(item: Any):
            if isinstance(item, dict):
                for key in list(item):
                    if key.lower() in {'authorization','api_key','apikey','image','image_url'}: item[key] = '[REDACTED]'
                    else: redact(item[key])
            elif isinstance(item, list):
                for child in item: redact(child)
            return item
        def scrub_paths(item: Any):
            if isinstance(item, dict):
                for key, value in item.items(): item[key] = scrub_paths(value)
            elif isinstance(item, list): return [scrub_paths(value) for value in item]
            elif isinstance(item, str) and (len(item) > 2 and item[1:3] in {':\\', ':/'}): return '[LOCAL_PATH_REDACTED]'
            return item
        redact(safe)
        safe = scrub_paths(safe)
        (root / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{purpose}.json").write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding='utf-8')

    def _request(self, purpose: str, data: dict[str, Any], images: list[bytes] | None = None, page_labels: list[int] | None = None) -> dict[str, Any]:
        if not self.base_url or not self.model:
            raise RuntimeError('AI_MODEL_NOT_CONFIGURED')
        if not self._is_local() and not self.allow_remote:
            raise RuntimeError('AI_PROVIDER_UNAVAILABLE')
        content: list[dict[str, Any]] = [{'type': 'text', 'text': purpose + '\nReturn one strict JSON object only.\n' + json.dumps(data, ensure_ascii=False)}]
        for index, raw in enumerate(images or []):
            if page_labels: content.append({'type': 'text', 'text': f'PAGE {page_labels[index]}'})
            content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(raw).decode('ascii')}})
        response_format: dict[str, Any] = {'type': 'json_object'}
        if self.structured_output == 'json_schema' and data.get('_schema'):
            response_format = {'type': 'json_schema', 'json_schema': {'name': data['_schema'], 'schema': SCHEMAS[data['_schema']]}}
        body = json.dumps({'model': self.model, 'messages': [{'role': 'user', 'content': content}],
                           'temperature': 0.1, 'response_format': response_format}).encode()
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        req = urllib.request.Request(self.base_url + '/chat/completions', data=body, headers=headers, method='POST')
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response: envelope = json.loads(response.read().decode('utf-8'))
                parsed = parse_json_response(envelope['choices'][0]['message']['content']); self._debug_response(purpose.split()[0].lower(), parsed)
                if attempt: parsed['_requestRetries'] = attempt
                return parsed
            except urllib.error.HTTPError as exc:
                code = 'AI_CONTEXT_TOO_LARGE' if exc.code == 413 else 'AI_PROVIDER_UNAVAILABLE'
                raise RuntimeError(code) from exc
            except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError) as exc:
                if attempt < self.max_retries: continue
                if isinstance(exc, (TimeoutError, socket.timeout)): raise TimeoutError('AI_REQUEST_TIMEOUT') from exc
                raise RuntimeError('AI_PROVIDER_UNAVAILABLE') from exc
            except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError('AI_RESPONSE_INVALID') from exc

    def probe(self) -> dict[str, Any]:
        # Tiny generated-in-code 1x1 JPEG; never sends user material.
        image = base64.b64decode('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q==')
        value = self._request('Probe vision and structured JSON. Describe whether an image was received.', {'expected': {'vision': True, 'structured': True}}, [image])
        _PROBE_STATE.update({'reachable': True, 'visionVerified': value.get('vision') is True, 'structuredOutputVerified': isinstance(value, dict) and value.get('structured') is True, 'lastProbeAt': datetime.now(timezone.utc).isoformat()})
        return {**self.get_status(), 'probeResult': value}

    def analyze_comic_pages(self, pages: list[dict[str, Any]], context: dict[str, Any] | None = None) -> dict[str, Any]:
        images = [p['image'] for p in pages if p.get('image')]
        safe_pages = [{'page': p['page'], 'text': p.get('text', '')} for p in pages]
        return self._request(SEMANTIC_RULES + '\n' + schema_instruction('semantic'), {'_schema': 'semantic', 'pages': safe_pages, 'previousContext': context or {}}, images, [p['page'] for p in pages if p.get('image')])

    def adapt_story(self, analysis: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        return self._request('Adapt this source analysis into a child-safe story. Clearly separate Source Facts from Adapted Content, preserve evidence mappings, and list every creative change in adaptationNotes.\n' + schema_instruction('adapted_story'), {'_schema': 'adapted_story', 'analysis': analysis, 'settings': settings})

    def generate_episode(self, story: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        return self._request('Generate exactly the requested production Episode shots with grounded prompts and stable speaker keys. For Pre-A1 use 2-8 English words per line. imagePrompt must include stable character appearance, clothing, scene, composition, action start, and art style. videoPrompt must include action change, camera, environment motion, dialogue, and continuity.\n' + schema_instruction('episode'), {'_schema': 'episode', 'adaptedStory': story, 'settings': settings})
