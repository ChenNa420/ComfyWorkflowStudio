from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from PIL import Image

from backend.db import ROOT
from backend.gpt_director import GPTDirectorResult, GPTDirectorShot, GPTDirectorStore

JOB_ID_RE = re.compile(r'^gij-[a-f0-9]{32}$')
MIME_BY_FORMAT = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}
EXT_BY_MIME = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}
DEFAULT_CHATGPT_IMAGE_CDP_URL = 'http://127.0.0.1:9222'
DEFAULT_CHATGPT_IMAGE_GPT_URL = 'https://chatgpt.com/g/g-6aa62443216c819181e35cd36d02e486-tong-yu-gong-fang-aidong-hua-bian-ju-dao-yan'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GPTImageError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class NodeImageWorker:
    def __init__(self, root: Path = ROOT):
        self.root = root.resolve()
        self.tool = self.root / 'tools' / 'chatgpt-image' / 'worker.js'
        self.tool_dir = self.tool.parent
        self.profile_dir = self.root / 'storage' / 'chatgpt-image-browser' / 'profile'
        self.output_dir = self.root / 'storage' / 'chatgpt-image-worker'
        self.cdp_url = os.getenv('CWS_CHATGPT_IMAGE_CDP_URL', DEFAULT_CHATGPT_IMAGE_CDP_URL).strip()
        self.gpt_url = os.getenv('CWS_CHATGPT_IMAGE_URL', DEFAULT_CHATGPT_IMAGE_GPT_URL).strip()

    def _node(self) -> str:
        node = shutil.which('node')
        if not node:
            raise GPTImageError('NODE_NOT_FOUND', 'Node.js 20+ is required for the ChatGPT image worker')
        if not self.tool.is_file():
            raise GPTImageError('IMAGE_WORKER_MISSING', 'ChatGPT image worker is missing')
        if not (self.tool_dir / 'node_modules' / 'playwright-core').exists():
            raise GPTImageError('IMAGE_WORKER_NOT_INSTALLED', 'Run npm install in tools/chatgpt-image first')
        return node

    def _env(self, gpt_url: str | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault('CWS_CHATGPT_IMAGE_PROFILE_DIR', str(self.profile_dir))
        env.setdefault('CWS_CHATGPT_IMAGE_OUTPUT_DIR', str(self.output_dir))
        env['CWS_CHATGPT_IMAGE_CDP_URL'] = self.cdp_url
        env['CWS_CHATGPT_IMAGE_URL'] = str(gpt_url or self.gpt_url).strip()
        return env

    def installation_status(self) -> dict[str, Any]:
        node = shutil.which('node')
        installed = (self.tool_dir / 'node_modules' / 'playwright-core').exists()
        return {
            'node': bool(node),
            'worker': self.tool.is_file(),
            'dependencies': installed,
            'profileExists': self.profile_dir.is_dir(),
            'readyForCheck': bool(node and self.tool.is_file() and installed),
            'browserMode': 'cdp' if self.cdp_url else 'dedicated_profile',
            'cdpUrl': self.cdp_url,
            'gptUrl': self.gpt_url,
        }

    def _run(self, command: str, payload: dict | None = None, timeout: int = 300) -> dict:
        node = self._node()
        try:
            process = subprocess.run(
                [node, str(self.tool), command],
                input=json.dumps(payload or {}, ensure_ascii=False) if payload is not None else None,
                text=True,
                encoding='utf-8',
                errors='strict',
                capture_output=True,
                cwd=self.root,
                env=self._env(),
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GPTImageError('IMAGE_WORKER_TIMEOUT', f'ChatGPT image worker timed out during {command}') from exc
        lines = [line for line in process.stdout.splitlines() if line.strip()]
        try:
            value = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError as exc:
            raise GPTImageError('IMAGE_WORKER_BAD_RESPONSE', 'ChatGPT image worker returned invalid JSON') from exc
        if process.returncode != 0 or value.get('ok') is False:
            raise GPTImageError(
                str(value.get('code') or 'IMAGE_WORKER_FAILED'),
                str(value.get('message') or 'ChatGPT image worker failed'),
            )
        return value

    def check(self) -> dict:
        return self._run('check', timeout=60)

    def cdp_ready(self) -> bool:
        if not self.cdp_url:
            return True
        try:
            with urlopen(self.cdp_url.rstrip('/') + '/json/version', timeout=1.5) as response:
                return 200 <= int(response.status) < 300
        except Exception:
            return False

    def prepare_story(self, payload: dict) -> dict:
        return self._run('prepare-story', payload, timeout=120)

    def collect_story(self, payload: dict) -> dict:
        return self._run('collect-story', payload, timeout=210)

    def generate(self, payload: dict) -> dict:
        return self._run('generate', payload, timeout=660)

    def start_login(self, gpt_url: str | None = None) -> dict:
        self._node()
        env = self._env(gpt_url)
        flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0) if os.name == 'nt' else 0
        if os.name == 'nt':
            launcher = self.tool_dir / 'start-cdp-chrome.cmd'
            if launcher.is_file():
                subprocess.Popen(
                    ['cmd.exe', '/c', str(launcher)],
                    cwd=self.root,
                    env=env,
                    creationflags=flags,
                )
                return {
                    'started': True,
                    'browserMode': 'cdp',
                    'cdpUrl': self.cdp_url,
                    'gptUrl': str(gpt_url or self.gpt_url).strip(),
                    'message': 'Dedicated normal Chrome started. Sign in to ChatGPT and keep the window open.',
                }
        subprocess.Popen(
            [shutil.which('node') or 'node', str(self.tool), 'login'],
            cwd=self.root,
            env=env,
            creationflags=flags,
        )
        return {
            'started': True,
            'browserMode': 'dedicated_profile',
            'gptUrl': str(gpt_url or self.gpt_url).strip(),
            'message': 'Dedicated ChatGPT login browser started',
        }


class ImmediateExecutor:
    """Small synchronous executor for unit tests."""

    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)
        return None


class GPTImageService:
    def __init__(self, root: Path = ROOT, worker: NodeImageWorker | None = None, executor=None):
        self.root = root.resolve()
        self.director = GPTDirectorStore(self.root / 'storage' / 'gpt-director')
        self.worker = worker or NodeImageWorker(self.root)
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix='gpt-image')
        self.jobs_root = (self.root / 'storage' / 'gpt-image-jobs').resolve()
        self.frames_root = (self.root / 'storage' / 'gpt-director').resolve()
        self._lock = threading.Lock()

    @staticmethod
    def _atomic_write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def status(self) -> dict:
        return self.worker.installation_status()

    def check(self) -> dict:
        return self.worker.check()

    def login(self) -> dict:
        return self.worker.start_login()

    def prepare_story(self, task_id: str, prompt: str, gpt_url: str | None = None) -> dict:
        text = str(prompt or '').strip()
        if not text:
            raise GPTImageError('STORY_PROMPT_REQUIRED', 'GPT Director story prompt is required')
        if len(text) > 60000:
            raise GPTImageError('STORY_PROMPT_TOO_LARGE', 'GPT Director story prompt is too large')
        try:
            task = self.director.load_task(task_id)
        except ValueError as exc:
            raise GPTImageError('INVALID_TASK_ID', 'Invalid GPT Director task ID') from exc
        except FileNotFoundError as exc:
            raise GPTImageError('TASK_NOT_FOUND', 'GPT Director task not found') from exc

        selected_pages = [int(page) for page in task.source.selectedPages]
        if not selected_pages:
            raise GPTImageError('SOURCE_IMAGES_REQUIRED', 'GPT Director task has no selected source pages')

        target_url = str(gpt_url or getattr(self.worker, 'gpt_url', DEFAULT_CHATGPT_IMAGE_GPT_URL)).strip()
        cdp_ready = getattr(self.worker, 'cdp_ready', None)
        if callable(cdp_ready) and not cdp_ready():
            self.worker.start_login(target_url)
            time.sleep(2.0)

        api_base = os.getenv('CWS_STUDIO_API_URL', 'http://127.0.0.1:8100').rstrip('/')
        payload = {
            'taskId': task_id,
            'prompt': text,
            'gptUrl': target_url,
            'sourcePages': [
                {
                    'page': page,
                    'url': f'{api_base}/api/comic-story/gpt-director/tasks/{task_id}/pages/{page}/image',
                }
                for page in selected_pages
            ],
        }
        result = self.worker.prepare_story(payload)
        prep_path = self._story_prep_path(task_id)
        self._atomic_write(prep_path, {
            'taskId': task_id,
            'gptUrl': str(result.get('url') or target_url),
            'assistantBaseline': result.get('assistantBaseline') or {},
            'preparedAt': _now(),
        })
        return {
            'ok': True,
            'prepared': bool(result.get('prepared')),
            'sent': bool(result.get('sent')),
            'taskId': task_id,
            'sourcePages': selected_pages,
            'attachmentCount': int(result.get('attachmentCount') or len(selected_pages)),
            'promptLength': int(result.get('promptLength') or len(text)),
            'gptUrl': str(result.get('url') or target_url),
            'browserMode': str(result.get('browserMode') or 'cdp'),
            'watchingForResult': True,
        }

    def _story_prep_path(self, task_id: str) -> Path:
        self.director.load_task(task_id)
        path = (self.frames_root / task_id / 'story-prep.json').resolve()
        path.relative_to(self.frames_root)
        return path

    def collect_story(self, task_id: str, gpt_url: str | None = None, use_latest: bool = False) -> dict:
        try:
            task = self.director.load_task(task_id)
        except ValueError as exc:
            raise GPTImageError('INVALID_TASK_ID', 'Invalid GPT Director task ID') from exc
        except FileNotFoundError as exc:
            raise GPTImageError('TASK_NOT_FOUND', 'GPT Director task not found') from exc

        if task.status == 'COMPLETED':
            result = self.director.load_result(task_id)
            return {
                'ok': True,
                'pending': False,
                'repaired': False,
                'taskId': task_id,
                'status': task.status,
                'title': result.creativeStory.title if result else '',
                'shotCount': len(result.shots) if result else 0,
            }

        prep_path = self._story_prep_path(task_id)
        if prep_path.is_file():
            try:
                prep = json.loads(prep_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                raise GPTImageError('STORY_PREP_INVALID', 'Stored GPT story preparation state is invalid') from exc
        elif use_latest:
            prep = {
                'gptUrl': str(gpt_url or getattr(self.worker, 'gpt_url', DEFAULT_CHATGPT_IMAGE_GPT_URL)).strip(),
                'assistantBaseline': {'count': 0, 'lastHash': ''},
            }
        else:
            raise GPTImageError('STORY_PREP_REQUIRED', 'Prepare the GPT story draft before collecting the result')

        target_url = str(gpt_url or prep.get('gptUrl') or getattr(self.worker, 'gpt_url', DEFAULT_CHATGPT_IMAGE_GPT_URL)).strip()
        collected = self.worker.collect_story({
            'taskId': task_id,
            'gptUrl': target_url,
            'assistantBaseline': prep.get('assistantBaseline') or {},
        })
        if bool(collected.get('pending')):
            return {
                'ok': True,
                'pending': True,
                'repaired': False,
                'taskId': task_id,
                'status': task.status,
            }

        raw_result = collected.get('result')
        try:
            result = GPTDirectorResult.model_validate(raw_result)
            self.director.import_result(task_id, result)
            completed = self.director.complete(task_id)
        except Exception as exc:
            raise GPTImageError('DIRECTOR_INVALID_PRODUCTION_JSON', str(exc)) from exc

        prep_path.unlink(missing_ok=True)
        return {
            'ok': True,
            'pending': False,
            'repaired': bool(collected.get('repaired')),
            'repairMethod': collected.get('repairMethod'),
            'taskId': task_id,
            'status': completed.status,
            'title': result.creativeStory.title,
            'shotCount': len(result.shots),
        }

    def _job_path(self, job_id: str) -> Path:
        if not JOB_ID_RE.fullmatch(job_id):
            raise GPTImageError('INVALID_JOB_ID', 'Invalid ChatGPT image job ID')
        path = (self.jobs_root / f'{job_id}.json').resolve()
        path.relative_to(self.jobs_root)
        return path

    def _load_result_and_shot(self, task_id: str, shot_id: str) -> tuple[GPTDirectorResult, GPTDirectorShot, int]:
        try:
            self.director.load_task(task_id)
            result = self.director.load_result(task_id)
        except ValueError as exc:
            raise GPTImageError('INVALID_TASK_ID', 'Invalid GPT Director task ID') from exc
        except FileNotFoundError as exc:
            raise GPTImageError('TASK_NOT_FOUND', 'GPT Director task not found') from exc
        if result is None:
            raise GPTImageError('RESULT_REQUIRED', 'GPT Director story result is required before image generation')
        for index, shot in enumerate(result.shots):
            if str(shot.shotId) == str(shot_id):
                return result, shot, index
        raise GPTImageError('SHOT_NOT_FOUND', 'Shot not found in GPT Director result')

    def _frames_file(self, task_id: str) -> Path:
        try:
            self.director.load_task(task_id)
        except (ValueError, FileNotFoundError) as exc:
            raise GPTImageError('TASK_NOT_FOUND', 'GPT Director task not found') from exc
        path = (self.frames_root / task_id / 'frames.json').resolve()
        path.relative_to(self.frames_root)
        return path

    def _load_frames_map(self, task_id: str) -> dict[str, dict]:
        path = self._frames_file(task_id)
        if not path.is_file():
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}

    def frames(self, task_id: str) -> list[dict]:
        try:
            result = self.director.load_result(task_id)
        except (ValueError, FileNotFoundError) as exc:
            raise GPTImageError('TASK_NOT_FOUND', 'GPT Director task not found') from exc
        values = self._load_frames_map(task_id)
        if not result:
            return []
        return [
            values.get(str(shot.shotId)) or {'shotId': str(shot.shotId), 'status': 'MISSING'}
            for shot in result.shots
        ]

    def _write_frames_map(self, task_id: str, values: dict[str, dict]) -> None:
        self._atomic_write(self._frames_file(task_id), values)

    def create_job(self, task_id: str, shot_id: str, replace: bool = False) -> dict:
        result, shot, shot_index = self._load_result_and_shot(task_id, shot_id)
        prompt = str(shot.imagePrompt or '').strip()
        if not prompt:
            raise GPTImageError('IMAGE_PROMPT_REQUIRED', 'Shot imagePrompt is required for GPT keyframe generation')
        with self._lock:
            frames = self._load_frames_map(task_id)
            if str(shot_id) in frames and not replace:
                raise GPTImageError('FRAME_EXISTS', 'This shot already has a frame; explicit replacement is required')
            job_id = f'gij-{uuid.uuid4().hex}'
            job = {
                'jobId': job_id,
                'taskId': task_id,
                'shotId': str(shot_id),
                'status': 'QUEUED',
                'replace': bool(replace),
                'createdAt': _now(),
                'startedAt': None,
                'completedAt': None,
                'errorCode': None,
                'errorMessage': None,
                'frame': None,
            }
            self._atomic_write(self._job_path(job_id), job)
        task = self.director.load_task(task_id)
        job['promptMode'] = 'direct'
        job['promptLength'] = len(prompt)
        job['promptSha256'] = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
        self._atomic_write(self._job_path(job_id), job)
        payload = {
            'taskId': task_id,
            'shotId': str(shot_id),
            'prompt': prompt,
            'promptMode': 'direct',
            'negativePrompt': shot.negativePrompt,
            'aspectRatio': task.settings.aspectRatio,
            'characterProfile': json.dumps(result.characterDefinitions, ensure_ascii=False)[:4000],
            'styleProfile': task.settings.style[:4000],
        }
        self.executor.submit(self._run_job, job_id, payload, shot_index)
        return job

    def get_job(self, job_id: str) -> dict:
        path = self._job_path(job_id)
        if not path.is_file():
            raise GPTImageError('JOB_NOT_FOUND', 'ChatGPT image job not found')
        return json.loads(path.read_text(encoding='utf-8'))

    @staticmethod
    def _validate_image(path: Path, max_bytes: int = 25 * 1024 * 1024) -> dict:
        if not path.is_file():
            raise GPTImageError('FRAME_FILE_MISSING', 'Generated image file is missing')
        size = path.stat().st_size
        if size <= 0 or size > max_bytes:
            raise GPTImageError('FRAME_SIZE_INVALID', 'Generated image has an invalid file size')
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                fmt = str(image.format or '').upper()
                width, height = image.size
        except Exception as exc:
            raise GPTImageError('FRAME_DECODE_FAILED', 'Generated image could not be decoded') from exc
        mime = MIME_BY_FORMAT.get(fmt)
        if not mime:
            raise GPTImageError('FRAME_MIME_UNSUPPORTED', f'Unsupported generated image format: {fmt}')
        if width < 256 or height < 256:
            raise GPTImageError('FRAME_DIMENSIONS_INVALID', 'Generated image is unexpectedly small')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {'sha256': digest, 'mime': mime, 'bytes': size, 'width': width, 'height': height}

    def _run_job(self, job_id: str, payload: dict, shot_index: int) -> None:
        job = self.get_job(job_id)
        job['status'] = 'RUNNING'
        job['startedAt'] = _now()
        self._atomic_write(self._job_path(job_id), job)
        try:
            response = self.worker.generate(payload)
            image = response.get('image') or {}
            source = Path(str(image.get('filePath') or '')).resolve()
            worker_root = (self.root / 'storage' / 'chatgpt-image-worker').resolve()
            source.relative_to(worker_root)
            details = self._validate_image(source)
            extension = EXT_BY_MIME[details['mime']]
            frame_dir = (self.frames_root / job['taskId'] / 'frames').resolve()
            frame_dir.relative_to(self.frames_root)
            frame_dir.mkdir(parents=True, exist_ok=True)
            target = frame_dir / f"shot-{shot_index + 1:03d}-{details['sha256'][:10]}.{extension}"
            shutil.copy2(source, target)
            record = {
                'frameAssetId': f"frame-{details['sha256'][:16]}",
                'taskId': job['taskId'],
                'shotId': job['shotId'],
                'status': 'IMPORTED',
                'sha256': details['sha256'],
                'mime': details['mime'],
                'bytes': details['bytes'],
                'width': details['width'],
                'height': details['height'],
                'captureMethod': str(image.get('captureMethod') or 'unknown'),
                'generatedAt': _now(),
                'source': 'chatgpt_web',
                'relativePath': str(target.relative_to(self.root)).replace('\\', '/'),
                'url': f"/api/gpt-image/tasks/{job['taskId']}/shots/{job['shotId']}/frame",
            }
            with self._lock:
                frames = self._load_frames_map(job['taskId'])
                old = frames.get(job['shotId'])
                frames[job['shotId']] = record
                self._write_frames_map(job['taskId'], frames)
                if old and old.get('relativePath') != record['relativePath']:
                    old_path = (self.root / str(old.get('relativePath') or '')).resolve()
                    try:
                        old_path.relative_to(frame_dir)
                        old_path.unlink(missing_ok=True)
                    except (ValueError, OSError):
                        pass
            job['status'] = 'COMPLETED'
            job['frame'] = record
        except GPTImageError as exc:
            job['status'] = 'FAILED'
            job['errorCode'] = exc.code
            job['errorMessage'] = str(exc)
        except Exception as exc:
            job['status'] = 'FAILED'
            job['errorCode'] = 'IMAGE_JOB_FAILED'
            job['errorMessage'] = str(exc)
        finally:
            job['completedAt'] = _now()
            self._atomic_write(self._job_path(job_id), job)

    def frame_file(self, task_id: str, shot_id: str) -> tuple[Path, dict]:
        self._load_result_and_shot(task_id, shot_id)
        record = self._load_frames_map(task_id).get(str(shot_id))
        if not record:
            raise GPTImageError('FRAME_NOT_FOUND', 'Frame not generated for this shot')
        target = (self.root / str(record.get('relativePath') or '')).resolve()
        allowed = (self.frames_root / task_id / 'frames').resolve()
        target.relative_to(allowed)
        if not target.is_file():
            raise GPTImageError('FRAME_FILE_MISSING', 'Stored frame file is missing')
        return target, record
