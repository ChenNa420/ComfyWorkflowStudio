from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TaskStatus = Literal['DRAFT', 'WAITING_GPT', 'RECEIVING', 'COMPLETED', 'FAILED']
TASK_ID_PATTERN = re.compile(r'^gdt-[a-f0-9]{32}$')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class GPTDirectorPage(StrictModel):
    ref: str
    page: int = Field(ge=1)
    imageUrl: str
    thumbnailUrl: str


class GPTDirectorSource(StrictModel):
    token: str = Field(min_length=1)
    name: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    pageCount: int = Field(ge=1)
    selectedPages: list[int] = Field(min_length=1, max_length=12)
    pages: list[GPTDirectorPage] = Field(min_length=1, max_length=12)


class GPTDirectorSettings(StrictModel):
    targetAge: str = '3-6岁'
    level: str = 'Pre-A1'
    style: str = '温馨冒险'
    language: str = '中英双语'
    duration: int = Field(default=30, ge=1, le=600)
    aspectRatio: str = '9:16'
    adaptationStrength: Literal['low', 'medium', 'high'] = 'low'
    preserveVisualMood: bool = True
    preserveComposition: bool = True
    replaceCharacters: bool = False
    allowEndingChange: bool = False
    extraRequest: str = ''


class GPTDirectorTask(StrictModel):
    id: str
    status: TaskStatus
    source: GPTDirectorSource
    settings: GPTDirectorSettings
    createdAt: str
    updatedAt: str
    resultHash: str | None = None


class GPTDirectorShot(StrictModel):
    shotId: str | int
    title: str = ''
    duration: float = Field(gt=0, le=10)
    storyPurpose: str = ''
    speaker: str | None = None
    english: str = ''
    chinese: str = ''
    keyframeDescription: str = ''
    imagePrompt: str = Field(min_length=1)
    videoPrompt: str = Field(min_length=1)
    negativePrompt: str = ''
    sourcePages: list[int] = Field(min_length=1)

    @field_validator('shotId')
    @classmethod
    def non_empty_shot_id(cls, value):
        if not str(value).strip():
            raise ValueError('shotId must not be empty')
        return value


class CreativeStory(StrictModel):
    title: str = Field(min_length=1)
    summary: str = ''
    story: str = ''
    adaptationNotes: list[str] = Field(default_factory=list)


class GPTDirectorResult(StrictModel):
    sourceUnderstanding: dict = Field(default_factory=dict)
    creativeStory: CreativeStory
    characterDefinitions: list[dict] = Field(default_factory=list)
    sceneDefinitions: list[dict] = Field(default_factory=list)
    shots: list[GPTDirectorShot] = Field(min_length=1, max_length=24)

    @model_validator(mode='after')
    def unique_shot_ids(self):
        ids = [str(shot.shotId) for shot in self.shots]
        if len(ids) != len(set(ids)):
            raise ValueError('shotId must be unique')
        return self


class GPTDirectorTaskCreate(StrictModel):
    token: str = Field(min_length=1)
    selectedPages: list[int] = Field(min_length=1, max_length=12)
    settings: GPTDirectorSettings = Field(default_factory=GPTDirectorSettings)

    @field_validator('selectedPages')
    @classmethod
    def valid_pages(cls, pages: list[int]):
        if any(page < 1 for page in pages):
            raise ValueError('selectedPages must be positive')
        if len(pages) != len(set(pages)):
            raise ValueError('selectedPages must not contain duplicates')
        return pages


class GPTDirectorResultImport(StrictModel):
    result: GPTDirectorResult


class GPTDirectorConflict(ValueError):
    pass


class GPTDirectorStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _directory(self, task_id: str) -> Path:
        if not TASK_ID_PATTERN.fullmatch(task_id):
            raise ValueError('invalid GPT Director taskId')
        target = (self.root / task_id).resolve()
        target.relative_to(self.root)
        return target

    @staticmethod
    def _atomic_write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def create(self, source: GPTDirectorSource, settings: GPTDirectorSettings) -> GPTDirectorTask:
        now = _now()
        task = GPTDirectorTask(id=f'gdt-{uuid.uuid4().hex}', status='WAITING_GPT', source=source,
                               settings=settings, createdAt=now, updatedAt=now)
        self._atomic_write(self._directory(task.id) / 'task.json', task.model_dump(mode='json'))
        return task

    @staticmethod
    def source_token_for_path(path: Path) -> str:
        resolved = path.resolve()
        return hashlib.sha256(str(resolved).encode('utf-8', errors='ignore')).hexdigest()[:24]

    def bind_local_source(self, task_id: str, token: str, source_path: Path) -> None:
        resolved = source_path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(str(resolved))
        if self.source_token_for_path(resolved) != token:
            raise ValueError('GPT Director source token does not match local path')
        self._atomic_write(
            self._directory(task_id) / 'source.local.json',
            {'token': token, 'path': str(resolved)},
        )

    def resolve_local_source(self, task_id: str, token: str) -> Path:
        binding_path = self._directory(task_id) / 'source.local.json'
        if not binding_path.is_file():
            raise FileNotFoundError('gpt_director_source_binding_not_found')
        try:
            payload = json.loads(binding_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError('invalid GPT Director local source binding') from exc
        if payload.get('token') != token or not isinstance(payload.get('path'), str):
            raise ValueError('invalid GPT Director local source binding')
        resolved = Path(payload['path']).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError('gpt_director_source_file_not_found')
        if self.source_token_for_path(resolved) != token:
            raise ValueError('GPT Director local source binding token mismatch')
        return resolved

    def load_task(self, task_id: str) -> GPTDirectorTask:
        path = self._directory(task_id) / 'task.json'
        if not path.is_file():
            raise FileNotFoundError(task_id)
        return GPTDirectorTask.model_validate_json(path.read_text(encoding='utf-8'))

    def load_result(self, task_id: str) -> GPTDirectorResult | None:
        path = self._directory(task_id) / 'result.json'
        return GPTDirectorResult.model_validate_json(path.read_text(encoding='utf-8')) if path.is_file() else None

    @staticmethod
    def result_hash(result: GPTDirectorResult) -> str:
        canonical = json.dumps(result.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    def import_result(self, task_id: str, result: GPTDirectorResult) -> tuple[GPTDirectorTask, bool]:
        task = self.load_task(task_id)
        allowed = set(task.source.selectedPages)
        if any(not set(shot.sourcePages).issubset(allowed) for shot in result.shots):
            raise ValueError('shot sourcePages must belong to task selectedPages')
        digest = self.result_hash(result)
        if task.resultHash == digest and self.load_result(task_id) is not None:
            return task, True
        if task.status == 'COMPLETED' or task.resultHash:
            raise GPTDirectorConflict('task already has a different result')
        self._atomic_write(self._directory(task_id) / 'result.json', result.model_dump(mode='json'))
        task.status = 'RECEIVING'
        task.resultHash = digest
        task.updatedAt = _now()
        self._atomic_write(self._directory(task_id) / 'task.json', task.model_dump(mode='json'))
        return task, False

    def complete(self, task_id: str) -> GPTDirectorTask:
        task = self.load_task(task_id)
        if self.load_result(task_id) is None:
            raise ValueError('task has no result')
        if task.status != 'COMPLETED':
            task.status = 'COMPLETED'
            task.updatedAt = _now()
            self._atomic_write(self._directory(task_id) / 'task.json', task.model_dump(mode='json'))
        return task


def build_episode_candidate(task: GPTDirectorTask, result: GPTDirectorResult) -> dict:
    return {
        'schemaVersion': 'gpt-director-1.0',
        'title': result.creativeStory.title,
        'story': result.creativeStory.story or result.creativeStory.summary,
        'style': task.settings.style,
        'audience': task.settings.targetAge,
        'language': task.settings.language,
        'level': task.settings.level,
        'aspectRatio': task.settings.aspectRatio,
        'duration': sum(shot.duration for shot in result.shots),
        'source': {'type': 'comic', 'name': task.source.filename, 'fileToken': task.source.token,
                   'pages': task.source.selectedPages},
        'characters': result.characterDefinitions,
        'scenes': result.sceneDefinitions,
        'shots': [
            {**shot.model_dump(mode='json'), 'id': index + 1, 'sourcePage': shot.sourcePages[0]}
            for index, shot in enumerate(result.shots)
        ],
    }
