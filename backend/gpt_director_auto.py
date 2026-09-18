from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from backend.db import ROOT
from backend.gpt_director import GPTDirectorStore

JOB_ID_RE = re.compile(r'^gda-[a-f0-9]{32}$')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GPTDirectorAutoError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class NodeDirectorRunner:
    def __init__(self, root: Path = ROOT):
        self.root = root.resolve()
        self.tool = self.root / 'tools' / 'webmcp' / 'gpt-director-runner.mjs'

    def _node(self) -> str:
        node = shutil.which('node')
        if not node:
            raise GPTDirectorAutoError('NODE_NOT_FOUND', 'Node.js 22+ is required for GPT Director auto mode')
        if not self.tool.is_file():
            raise GPTDirectorAutoError('DIRECTOR_RUNNER_MISSING', 'GPT Director auto runner is missing')
        if not (self.root / 'tools' / 'webmcp' / 'node_modules' / '@modelcontextprotocol' / 'client').exists():
            raise GPTDirectorAutoError('WEBMCP_DEPENDENCIES_MISSING', 'Run npm install --prefix tools/webmcp')
        if not (self.root / 'tools' / 'chatgpt-image' / 'node_modules' / 'playwright-core').exists():
            raise GPTDirectorAutoError('CHATGPT_BROWSER_DEPENDENCIES_MISSING', 'Run npm install --prefix tools/chatgpt-image')
        return node

    @staticmethod
    def _relay_ready() -> bool:
        try:
            with socket.create_connection(('127.0.0.1', 9333), timeout=1.5):
                return True
        except OSError:
            return False

    @staticmethod
    def _cdp_ready() -> bool:
        try:
            with urlopen('http://127.0.0.1:9222/json/version', timeout=2) as response:
                return 200 <= int(response.status) < 300
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        node = shutil.which('node')
        webmcp_dependencies = (self.root / 'tools' / 'webmcp' / 'node_modules' / '@modelcontextprotocol' / 'client').exists()
        browser_dependencies = (self.root / 'tools' / 'chatgpt-image' / 'node_modules' / 'playwright-core').exists()
        relay = self._relay_ready()
        cdp = self._cdp_ready()
        return {
            'node': bool(node),
            'runner': self.tool.is_file(),
            'webmcpDependencies': webmcp_dependencies,
            'browserDependencies': browser_dependencies,
            'relayReady': relay,
            'cdpReady': cdp,
            'ready': bool(node and self.tool.is_file() and webmcp_dependencies and browser_dependencies and relay and cdp),
            'relayUrl': 'ws://127.0.0.1:9333',
            'cdpUrl': 'http://127.0.0.1:9222',
        }

    def run(self, task_id: str, timeout: int = 780) -> dict[str, Any]:
        node = self._node()
        if not self._relay_ready():
            raise GPTDirectorAutoError('WEBMCP_RELAY_NOT_READY', 'WebMCP Relay is not running on 127.0.0.1:9333')
        if not self._cdp_ready():
            raise GPTDirectorAutoError('CHATGPT_CDP_NOT_READY', 'ChatGPT CDP Chrome is not running on 127.0.0.1:9222')
        try:
            process = subprocess.run(
                [node, str(self.tool), '--task-id', task_id],
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GPTDirectorAutoError('DIRECTOR_AUTO_TIMEOUT', 'GPT Director automatic run timed out') from exc

        lines = [line for line in process.stdout.splitlines() if line.strip()]
        try:
            payload = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError as exc:
            raise GPTDirectorAutoError('DIRECTOR_AUTO_BAD_RESPONSE', 'GPT Director runner returned invalid JSON') from exc

        if process.returncode != 0 or payload.get('ok') is False:
            message = str(payload.get('message') or 'GPT Director automatic run failed')
            raise GPTDirectorAutoError(str(payload.get('code') or 'DIRECTOR_AUTO_FAILED'), message)

        return {
            'result': payload,
            'stderrTail': '\n'.join(process.stderr.splitlines()[-30:])[-8000:],
        }


class ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)
        return None


class GPTDirectorAutoService:
    def __init__(self, root: Path = ROOT, runner: NodeDirectorRunner | None = None, executor=None):
        self.root = root.resolve()
        self.director = GPTDirectorStore(self.root / 'storage' / 'gpt-director')
        self.runner = runner or NodeDirectorRunner(self.root)
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix='gpt-director-auto')
        self.jobs_root = (self.root / 'storage' / 'gpt-director-auto-jobs').resolve()
        self._lock = threading.Lock()

    @staticmethod
    def _atomic_write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def status(self) -> dict[str, Any]:
        return self.runner.status()

    def recover_interrupted_jobs(self) -> int:
        if not self.jobs_root.exists():
            return 0
        recovered = 0
        for path in self.jobs_root.glob('gda-*.json'):
            try:
                job = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            if job.get('status') not in {'QUEUED', 'RUNNING'}:
                continue
            job['status'] = 'FAILED'
            job['completedAt'] = _now()
            job['errorCode'] = 'DIRECTOR_AUTO_INTERRUPTED'
            job['errorMessage'] = (
                'GPT Director automatic run was interrupted by a backend restart. '
                'Start a new automatic run.'
            )
            self._atomic_write(path, job)
            recovered += 1
        return recovered

    def _job_path(self, job_id: str) -> Path:
        if not JOB_ID_RE.fullmatch(job_id):
            raise GPTDirectorAutoError('INVALID_JOB_ID', 'Invalid GPT Director auto job ID')
        target = (self.jobs_root / (job_id + '.json')).resolve()
        target.relative_to(self.jobs_root)
        return target

    def get_job(self, job_id: str) -> dict:
        path = self._job_path(job_id)
        if not path.is_file():
            raise GPTDirectorAutoError('JOB_NOT_FOUND', 'GPT Director auto job not found')
        return json.loads(path.read_text(encoding='utf-8'))

    def create_job(self, task_id: str) -> dict:
        try:
            task = self.director.load_task(task_id)
        except ValueError as exc:
            raise GPTDirectorAutoError('INVALID_TASK_ID', 'Invalid GPT Director task ID') from exc
        except FileNotFoundError as exc:
            raise GPTDirectorAutoError('TASK_NOT_FOUND', 'GPT Director task not found') from exc

        if task.status == 'COMPLETED':
            raise GPTDirectorAutoError('TASK_ALREADY_COMPLETED', 'GPT Director task is already completed')
        if self.director.load_result(task_id) is not None:
            raise GPTDirectorAutoError('TASK_ALREADY_HAS_RESULT', 'GPT Director task already has a result')

        with self._lock:
            job_id = 'gda-' + uuid.uuid4().hex
            job = {
                'jobId': job_id,
                'taskId': task_id,
                'status': 'QUEUED',
                'createdAt': _now(),
                'startedAt': None,
                'completedAt': None,
                'errorCode': None,
                'errorMessage': None,
                'result': None,
            }
            self._atomic_write(self._job_path(job_id), job)
        self.executor.submit(self._run_job, job_id)
        return job

    def _run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        job['status'] = 'RUNNING'
        job['startedAt'] = _now()
        self._atomic_write(self._job_path(job_id), job)
        try:
            response = self.runner.run(job['taskId'])
            summary = response.get('result') or {}
            task = self.director.load_task(job['taskId'])
            result = self.director.load_result(job['taskId'])
            if task.status != 'COMPLETED' or result is None:
                raise GPTDirectorAutoError('DIRECTOR_RESULT_NOT_COMPLETED', 'Runner finished but the GPT Director result was not completed')
            job['status'] = 'COMPLETED'
            job['result'] = {
                'title': str(summary.get('title') or result.creativeStory.title),
                'shotCount': int(summary.get('shotCount') or len(result.shots)),
                'sourcePages': list(summary.get('sourcePages') or task.source.selectedPages),
            }
            if response.get('stderrTail'):
                job['runtimeLogTail'] = str(response['stderrTail'])
        except GPTDirectorAutoError as exc:
            job['status'] = 'FAILED'
            job['errorCode'] = exc.code
            job['errorMessage'] = str(exc)
        except Exception as exc:
            job['status'] = 'FAILED'
            job['errorCode'] = 'DIRECTOR_AUTO_JOB_FAILED'
            job['errorMessage'] = str(exc)
        finally:
            job['completedAt'] = _now()
            self._atomic_write(self._job_path(job_id), job)
