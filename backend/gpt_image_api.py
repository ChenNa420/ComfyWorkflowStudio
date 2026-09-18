from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.db import ROOT
from backend.gpt_image_service import GPTImageError, GPTImageService


logger = logging.getLogger("comfy.gpt_image")


class GenerateFrameRequest(BaseModel):
    replace: bool = False


class PrepareStoryRequest(BaseModel):
    prompt: str
    gptUrl: str | None = None


class CollectStoryRequest(BaseModel):
    gptUrl: str | None = None
    useLatest: bool = False


def gpt_image_router() -> APIRouter:
    router = APIRouter(prefix='/api/gpt-image', tags=['gpt-image'])
    service = GPTImageService(ROOT)

    def public_frame(value: dict) -> dict:
        return {key: item for key, item in value.items() if key != 'relativePath'}

    def public_job(value: dict) -> dict:
        result = dict(value)
        if isinstance(result.get('frame'), dict):
            result['frame'] = public_frame(result['frame'])
        return result

    def fail(exc: GPTImageError):
        status = (
            404 if exc.code in {'TASK_NOT_FOUND', 'SHOT_NOT_FOUND', 'JOB_NOT_FOUND', 'FRAME_NOT_FOUND', 'FRAME_FILE_MISSING'}
            else 409 if exc.code in {'FRAME_EXISTS', 'RESULT_REQUIRED'}
            else 400
        )
        logger.warning("GPT image API failed [%s] %s", exc.code, str(exc))
        raise HTTPException(status_code=status, detail={'code': exc.code, 'message': str(exc)}) from exc

    @router.get('/status')
    def status():
        return service.status()

    @router.post('/check')
    def check():
        try:
            return service.check()
        except GPTImageError as exc:
            fail(exc)

    @router.post('/login')
    def login():
        try:
            return service.login()
        except GPTImageError as exc:
            fail(exc)

    @router.post('/tasks/{task_id}/prepare-story')
    def prepare_story(task_id: str, payload: PrepareStoryRequest):
        try:
            return service.prepare_story(task_id, payload.prompt, payload.gptUrl)
        except GPTImageError as exc:
            fail(exc)

    @router.post('/tasks/{task_id}/collect-story')
    def collect_story(task_id: str, payload: CollectStoryRequest):
        try:
            return service.collect_story(task_id, payload.gptUrl, payload.useLatest)
        except GPTImageError as exc:
            fail(exc)

    @router.post('/tasks/{task_id}/shots/{shot_id}/generate')
    def generate(task_id: str, shot_id: str, payload: GenerateFrameRequest):
        try:
            return public_job(service.create_job(task_id, shot_id, replace=payload.replace))
        except GPTImageError as exc:
            fail(exc)

    @router.get('/jobs/{job_id}')
    def job(job_id: str):
        try:
            return public_job(service.get_job(job_id))
        except GPTImageError as exc:
            fail(exc)

    @router.get('/tasks/{task_id}/frames')
    def frames(task_id: str):
        try:
            return {'taskId': task_id, 'frames': [public_frame(item) for item in service.frames(task_id)]}
        except GPTImageError as exc:
            fail(exc)

    @router.get('/tasks/{task_id}/shots/{shot_id}/frame')
    def frame(task_id: str, shot_id: str):
        try:
            path, record = service.frame_file(task_id, shot_id)
        except GPTImageError as exc:
            fail(exc)
        return FileResponse(path, media_type=record['mime'], filename=path.name, content_disposition_type='inline')

    return router
