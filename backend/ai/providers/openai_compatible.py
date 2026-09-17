from __future__ import annotations

import base64
import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from backend.ai.schema_prompt import schema_instruction, SCHEMAS


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

    def _is_local(self) -> bool:
        return (urlsplit(self.base_url).hostname or '').lower() in {'localhost', '127.0.0.1', '::1'}

    def get_status(self) -> dict[str, Any]:
        endpoint_allowed = self._is_local() or self.allow_remote
        configured = bool(self.base_url and self.model and endpoint_allowed)
        return {'provider': self.name, 'enabled': True, 'configured': configured,
                'model': self.model or None, 'baseUrlSafe': safe_base_url(self.base_url),
                'supportsVision': True, 'remoteAllowed': self.allow_remote, 'isLocalEndpoint': self._is_local(),
                'reason': None if configured else ('Remote endpoint requires COMIC_AI_ALLOW_REMOTE=true' if self.base_url and self.model else 'COMIC_AI_BASE_URL and COMIC_AI_MODEL are required')}

    def _request(self, purpose: str, data: dict[str, Any], images: list[bytes] | None = None) -> dict[str, Any]:
        if not self.base_url or not self.model:
            raise RuntimeError('AI_MODEL_NOT_CONFIGURED')
        if not self._is_local() and not self.allow_remote:
            raise RuntimeError('AI_PROVIDER_UNAVAILABLE')
        content: list[dict[str, Any]] = [{'type': 'text', 'text': purpose + '\nReturn one strict JSON object only.\n' + json.dumps(data, ensure_ascii=False)}]
        for raw in images or []:
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
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                envelope = json.loads(response.read().decode('utf-8'))
            return parse_json_response(envelope['choices'][0]['message']['content'])
        except (TimeoutError, socket.timeout) as exc:
            raise TimeoutError('AI_REQUEST_TIMEOUT') from exc
        except urllib.error.HTTPError as exc:
            code = 'AI_CONTEXT_TOO_LARGE' if exc.code == 413 else 'AI_PROVIDER_UNAVAILABLE'
            raise RuntimeError(code) from exc
        except (urllib.error.URLError, ConnectionError) as exc:
            raise RuntimeError('AI_PROVIDER_UNAVAILABLE') from exc
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError('AI_RESPONSE_INVALID') from exc

    def analyze_comic_pages(self, pages: list[dict[str, Any]], context: dict[str, Any] | None = None) -> dict[str, Any]:
        images = [p['image'] for p in pages if p.get('image')]
        safe_pages = [{'page': p['page'], 'text': p.get('text', '')} for p in pages]
        return self._request('Analyze comic pages with evidence and uncertainty.\n' + schema_instruction('semantic'), {'_schema': 'semantic', 'pages': safe_pages, 'previousContext': context or {}}, images)

    def adapt_story(self, analysis: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        return self._request('Adapt this source analysis into a child-safe story. Preserve evidence mappings.\n' + schema_instruction('adapted_story'), {'_schema': 'adapted_story', 'analysis': analysis, 'settings': settings})

    def generate_episode(self, story: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        return self._request('Generate a production Episode JSON with grounded prompts and stable speaker keys.\n' + schema_instruction('episode'), {'_schema': 'episode', 'adaptedStory': story, 'settings': settings})
