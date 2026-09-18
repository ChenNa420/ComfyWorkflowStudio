from __future__ import annotations

import json
import mimetypes
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request


class ComfyClientError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str = 'http://127.0.0.1:8188', timeout: int = 30) -> None:
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def _json_request(self, path: str, method: str = 'GET', payload: dict[str, Any] | None = None) -> Any:
        body = None
        headers = {'Accept': 'application/json'}
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        req = request.Request(f'{self.base_url}{path}', data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ComfyClientError(str(exc)) from exc
        if not raw:
            return None
        try:
            return json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComfyClientError(f'Invalid JSON response from {path}') from exc

    def system_stats(self) -> dict[str, Any]:
        value = self._json_request('/system_stats')
        return value if isinstance(value, dict) else {}

    def object_info(self) -> dict[str, Any]:
        value = self._json_request('/object_info')
        return value if isinstance(value, dict) else {}

    def queue(self) -> dict[str, Any]:
        value = self._json_request('/queue')
        return value if isinstance(value, dict) else {}

    def submit_prompt(self, prompt: dict[str, Any], client_id: str | None = None) -> dict[str, Any]:
        payload = {'prompt': prompt, 'client_id': client_id or str(uuid.uuid4())}
        value = self._json_request('/prompt', method='POST', payload=payload)
        if not isinstance(value, dict):
            raise ComfyClientError('ComfyUI returned an invalid prompt response')
        return value

    def history(self, prompt_id: str) -> dict[str, Any]:
        value = self._json_request(f'/history/{parse.quote(prompt_id)}')
        return value if isinstance(value, dict) else {}

    def wait_for_history(self, prompt_id: str, timeout: int = 900, interval: float = 2.0) -> dict[str, Any]:
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            history = self.history(prompt_id)
            if prompt_id in history:
                return history[prompt_id]
            time.sleep(interval)
        raise ComfyClientError(f'Timed out waiting for prompt {prompt_id}')

    def upload_image(self, path: str | Path, overwrite: bool = False) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.is_file():
            raise ComfyClientError(f'Image does not exist: {file_path}')

        boundary = f'----ComfyWorkflowStudio{uuid.uuid4().hex}'
        filename = file_path.name
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        chunks: list[bytes] = []

        def field(name: str, value: str) -> None:
            chunks.append(f'--{boundary}\r\n'.encode())
            chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            chunks.append(value.encode('utf-8'))
            chunks.append(b'\r\n')

        chunks.append(f'--{boundary}\r\n'.encode())
        chunks.append(f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode('utf-8'))
        chunks.append(f'Content-Type: {content_type}\r\n\r\n'.encode())
        chunks.append(file_path.read_bytes())
        chunks.append(b'\r\n')
        field('type', 'input')
        field('overwrite', 'true' if overwrite else 'false')
        chunks.append(f'--{boundary}--\r\n'.encode())

        req = request.Request(
            f'{self.base_url}/upload/image',
            data=b''.join(chunks),
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}', 'Accept': 'application/json'},
            method='POST',
        )
        try:
            with request.urlopen(req, timeout=max(self.timeout, 60)) as response:
                raw = response.read()
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ComfyClientError(str(exc)) from exc
        try:
            value = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComfyClientError('Invalid upload response') from exc
        if not isinstance(value, dict):
            raise ComfyClientError('Invalid upload response')
        return value

    def download_view(self, filename: str, subfolder: str = '', file_type: str = 'output') -> bytes:
        query = parse.urlencode({'filename': filename, 'subfolder': subfolder, 'type': file_type})
        req = request.Request(f'{self.base_url}/view?{query}', method='GET')
        try:
            with request.urlopen(req, timeout=max(self.timeout, 120)) as response:
                return response.read()
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ComfyClientError(str(exc)) from exc


def comfy_url_from_env() -> str:
    return os.getenv('COMFYUI_URL', 'http://127.0.0.1:8188')
