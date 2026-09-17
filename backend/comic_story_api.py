from __future__ import annotations

import hashlib
import mimetypes
import re
import zipfile
from datetime import datetime
from collections import Counter
from pathlib import Path

import fitz
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from backend.db import ROOT
from backend.ai.providers import get_comic_ai_provider
from backend.ai.service import ComicAiError, ComicAiService

SUPPORTED_FILES = {'.pdf', '.cbz', '.zip', '.png', '.jpg', '.jpeg', '.webp'}
IMAGE_FILES = {'.png', '.jpg', '.jpeg', '.webp'}
_FILE_REGISTRY: dict[str, Path] = {}
_ALLOWED_ROOTS: set[Path] = set()


class ComicScanRequest(BaseModel):
    path: str


class ComicSourceRequest(BaseModel):
    path: str
    limit: int = Field(default=200, ge=1, le=1000)


class ComicAnalyzeRequest(BaseModel):
    token: str
    startPage: int = Field(default=1, ge=1)
    endPage: int | None = Field(default=None, ge=1)
    forceRefresh: bool = False


class ComicAdaptRequest(BaseModel):
    semanticAnalysisId: str
    style: str = '温馨治愈'
    audience: str = '3-8岁儿童'
    language: str = '中文（简体）'
    level: str = 'Pre-A1'
    educationGoals: list[str] = Field(default_factory=list)
    fidelity: str = 'balanced'
    preserveCharacterNames: bool = True
    preserveCorePlot: bool = True
    preserveDialogue: bool = False
    shotCount: int = Field(default=6, ge=1, le=12)
    aspectRatio: str = '9:16'


class ComicEpisodeRequest(BaseModel):
    adaptedStory: dict
    settings: dict = Field(default_factory=dict)


class ComicDraftRequest(BaseModel):
    token: str
    title: str = ''
    style: str = '温馨治愈'
    audience: str = '3-8岁儿童'
    language: str = '中文（简体）'
    shotCount: int = Field(default=6, ge=1, le=24)
    aspectRatio: str = '9:16'
    level: str = 'Pre-A1'
    duration: int = Field(default=30, ge=5, le=600)
    fidelity: str = 'balanced'
    adaptationStrength: str = 'medium'
    educationalGoal: str = ''
    preserveCharacterNames: bool = True
    preserveDialogues: bool = True
    autoShotCount: bool = False
    startPage: int = Field(default=1, ge=1)
    endPage: int | None = Field(default=None, ge=1)


def _clean_path(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail='comic_path_not_found')
    return path


def _is_supported(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_FILES


def _files_under(path: Path, limit: int = 1000) -> list[Path]:
    if path.is_file():
        return [path] if _is_supported(path) else []
    values: list[Path] = []
    for item in path.rglob('*'):
        if _is_supported(item):
            values.append(item)
            if len(values) >= limit:
                break
    return sorted(values, key=lambda item: str(item).lower())


def _register_file(path: Path) -> str:
    value = str(path.resolve()).encode('utf-8', errors='ignore')
    token = hashlib.sha256(value).hexdigest()[:24]
    _FILE_REGISTRY[token] = path.resolve()
    return token


def _assert_registered(token: str) -> Path:
    path = _FILE_REGISTRY.get(token)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail='comic_file_token_not_found')
    return path


def _page_count(path: Path) -> int | None:
    suffix = path.suffix.lower()
    try:
        if suffix == '.pdf':
            with fitz.open(path) as doc:
                return doc.page_count
        if suffix in {'.cbz', '.zip'}:
            with zipfile.ZipFile(path) as archive:
                return len([name for name in archive.namelist() if Path(name).suffix.lower() in IMAGE_FILES])
        if suffix in IMAGE_FILES:
            return 1
    except (OSError, RuntimeError, zipfile.BadZipFile):
        return None
    return None


def _issue_payload(path: Path) -> dict:
    token = _register_file(path)
    return {
        'token': token,
        'name': path.stem,
        'filename': path.name,
        'extension': path.suffix.lower().lstrip('.'),
        'sizeBytes': path.stat().st_size,
        'pageCount': _page_count(path),
        'coverUrl': f'/api/comic-story/page/{token}/1?thumbnail=true',
        'fileUrl': f'/api/comic-story/file/{token}',
        'modifiedAt': datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        'folder': path.parent.name,
        'error': None,
    }


def _collection_payload(path: Path) -> dict | None:
    files = _files_under(path, 1000)
    if not files:
        return None
    size = 0
    formats: Counter[str] = Counter()
    for file in files:
        try:
            size += file.stat().st_size
        except OSError:
            pass
        formats[file.suffix.lower().lstrip('.') or 'file'] += 1
    return {
        'name': path.name,
        'path': str(path),
        'kind': 'folder' if path.is_dir() else 'file',
        'itemCount': len(files),
        'sizeBytes': size,
        'formats': dict(formats),
    }


def _candidate_roots() -> list[str]:
    found: list[str] = []
    keywords = ('漫画', '杂志', 'comic', 'manga', 'highlights', 'beano')
    bases = [Path('F:/BaiduNetdiskDownload'), Path('D:/BaiduNetdiskDownload'), Path.home() / 'Downloads']
    for base in bases:
        if not base.is_dir():
            continue
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and any(key in child.name.lower() for key in keywords):
                found.append(str(child.resolve()))
    return list(dict.fromkeys(found))[:20]


def _extract_pdf_text(path: Path, start_page: int, end_page: int | None) -> tuple[int, list[dict]]:
    with fitz.open(path) as doc:
        total = doc.page_count
        start = max(1, min(start_page, total))
        end = max(start, min(end_page or min(start + 9, total), total))
        pages: list[dict] = []
        for number in range(start, end + 1):
            text = re.sub(r'\s+', ' ', doc.load_page(number - 1).get_text('text')).strip()
            pages.append({'page': number, 'text': text[:5000]})
        return total, pages


def _source_pages(path: Path, start_page: int, end_page: int | None) -> tuple[int, list[dict]]:
    if path.suffix.lower() == '.pdf':
        return _extract_pdf_text(path, start_page, end_page)
    total = _page_count(path) or 1
    start = max(1, min(start_page, total))
    end = max(start, min(end_page or min(start + 9, total), total))
    return total, [{'page': number, 'text': ''} for number in range(start, end + 1)]


def _first_sentence(text: str) -> str:
    if not text:
        return ''
    pieces = re.split(r'(?<=[.!?。！？])\s+', text.strip())
    return (pieces[0] if pieces else text)[:280]


def _service():
    return ComicAiService(get_comic_ai_provider(), ROOT / 'storage' / 'comic-analysis')


def _cache_target(analysis_id: str) -> Path:
    if not re.fullmatch(r'[a-f0-9]{24}', analysis_id):
        raise HTTPException(status_code=400, detail={'code': 'INVALID_SEMANTIC_ANALYSIS_ID'})
    root = (ROOT / 'storage' / 'comic-analysis').resolve()
    target = (root / f'{analysis_id}.json').resolve()
    try: target.relative_to(root)
    except ValueError as exc: raise HTTPException(status_code=400, detail={'code': 'INVALID_SEMANTIC_ANALYSIS_ID'}) from exc
    return target


def _ai_error(exc: ComicAiError):
    status = 409 if exc.code in {'AI_PROVIDER_DISABLED', 'AI_MODEL_NOT_CONFIGURED'} else 413 if exc.code == 'AI_CONTEXT_TOO_LARGE' else 502
    raise HTTPException(status_code=status, detail={'code': exc.code, 'message': str(exc)}) from exc


def comic_story_router() -> APIRouter:
    router = APIRouter(prefix='/api/comic-story', tags=['comic-story'])

    @router.get('/suggested-roots')
    def suggested_roots():
        provider = get_comic_ai_provider()
        return {'roots': _candidate_roots(), 'provider': {'name': provider.name, 'enabled': provider.enabled}}

    @router.get('/ai/status')
    def ai_status():
        try:
            return _service().status()
        except RuntimeError as exc:
            return {'provider': 'unknown', 'enabled': False, 'configured': False, 'model': None,
                    'baseUrlSafe': '', 'supportsVision': False, 'reason': str(exc)}

    @router.post('/ai/probe')
    def ai_probe():
        try: return _service().probe()
        except ComicAiError as exc: _ai_error(exc)

    @router.post('/scan')
    def scan_library(payload: ComicScanRequest):
        root = _clean_path(payload.path)
        if not root.is_dir():
            raise HTTPException(status_code=400, detail='comic_root_must_be_directory')
        _ALLOWED_ROOTS.add(root)
        collections = []
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            value = _collection_payload(child)
            if value:
                collections.append(value)
        return {'root': str(root), 'collections': collections, 'count': len(collections)}

    @router.post('/issues')
    def list_issues(payload: ComicSourceRequest):
        source = _clean_path(payload.path)
        if not any(source == root or root in source.parents for root in _ALLOWED_ROOTS):
            raise HTTPException(status_code=403, detail='comic_source_not_scanned')
        files = _files_under(source, payload.limit)
        issue_values = []
        for path in files:
            try:
                issue_values.append(_issue_payload(path))
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                issue_values.append({'token': '', 'name': path.stem, 'filename': path.name, 'extension': path.suffix.lower().lstrip('.'), 'sizeBytes': 0, 'pageCount': None, 'coverUrl': '', 'fileUrl': '', 'folder': path.parent.name, 'error': type(exc).__name__})
        return {
            'source': str(source),
            'issues': issue_values,
            'count': len(files),
        }

    @router.get('/file/{token}')
    def comic_file(token: str):
        path = _assert_registered(token)
        media_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        return FileResponse(path, media_type=media_type, filename=path.name, content_disposition_type='inline')

    @router.get('/page/{token}/{page_number}')
    def comic_page(token: str, page_number: int, thumbnail: bool = False):
        path = _assert_registered(token)
        if page_number < 1:
            raise HTTPException(status_code=400, detail='page_number_must_be_positive')
        suffix = path.suffix.lower()
        if suffix in IMAGE_FILES:
            if page_number != 1:
                raise HTTPException(status_code=404, detail='comic_page_not_found')
            return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or 'image/jpeg')
        if suffix == '.pdf':
            try:
                with fitz.open(path) as doc:
                    if page_number > doc.page_count:
                        raise HTTPException(status_code=404, detail='comic_page_not_found')
                    page = doc.load_page(page_number - 1)
                    scale = 0.35 if thumbnail else 0.75
                    quality = 68 if thumbnail else 80
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    return Response(pix.tobytes('jpeg', jpg_quality=quality), media_type='image/jpeg')
            except RuntimeError as exc:
                raise HTTPException(status_code=422, detail='comic_pdf_render_failed') from exc

        if suffix in {'.cbz', '.zip'}:
            try:
                with zipfile.ZipFile(path) as archive:
                    names = sorted(name for name in archive.namelist() if Path(name).suffix.lower() in IMAGE_FILES)
                    if page_number > len(names):
                        raise HTTPException(status_code=404, detail='comic_page_not_found')
                    name = names[page_number - 1]
                    info = archive.getinfo(name)
                    from backend.ai.service import MAX_ARCHIVE_IMAGE_BYTES, MAX_ARCHIVE_TOTAL_BYTES, MAX_ARCHIVE_COMPRESSION_RATIO
                    infos = [archive.getinfo(n) for n in names]
                    if sum(i.file_size for i in infos) > MAX_ARCHIVE_TOTAL_BYTES or info.file_size > MAX_ARCHIVE_IMAGE_BYTES:
                        raise HTTPException(status_code=413, detail='COMIC_ARCHIVE_TOO_LARGE')
                    if info.file_size / max(1, info.compress_size) > MAX_ARCHIVE_COMPRESSION_RATIO:
                        raise HTTPException(status_code=422, detail='COMIC_ARCHIVE_UNSAFE')
                    data = archive.read(info)
                    media_type = mimetypes.guess_type(name)[0] or 'image/jpeg'
                    return Response(data, media_type=media_type)
            except zipfile.BadZipFile as exc:
                raise HTTPException(status_code=422, detail='comic_archive_invalid') from exc
        raise HTTPException(status_code=415, detail='comic_preview_unsupported')

    @router.post('/analyze')
    def analyze_source(payload: ComicAnalyzeRequest):
        path = _assert_registered(payload.token)
        total, pages = _source_pages(path, payload.startPage, payload.endPage)
        combined = ' '.join(item['text'] for item in pages if item['text'])
        words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", combined)
        common = [word for word, _ in Counter(word.lower() for word in words).most_common(12)]
        provider = get_comic_ai_provider()
        return {
            'token': payload.token,
            'sourceName': path.stem,
            'pageCount': total,
            'selectedPages': [item['page'] for item in pages],
            'pages': pages,
            'textExcerpt': combined[:6000],
            'keywords': common,
            'analysisMode': 'local-source-extraction',
            'aiReady': False,
            'provider': {'name': provider.name, 'enabled': provider.enabled},
            'semanticAnalysis': {'status': 'pending', 'characters': [], 'scenes': [], 'dialogues': [], 'plotEvents': [], 'props': [], 'locations': []},
            'requiresAiEnrichment': not provider.enabled,
            'message': '已完成本地页面与文本提取；角色、场景、剧情语义分析将在 AI Provider 接入后增强。',
        }

    @router.post('/semantic-analyze')
    def semantic_analyze(payload: ComicAnalyzeRequest):
        path = _assert_registered(payload.token)
        _, pages = _source_pages(path, payload.startPage, payload.endPage)
        try:
            return _service().analyze(path, payload.token, pages, payload.forceRefresh)
        except ComicAiError as exc:
            _ai_error(exc)

    @router.post('/adapt-story')
    def adapt_story(payload: ComicAdaptRequest):
        cache = _cache_target(payload.semanticAnalysisId)
        if not cache.is_file():
            raise HTTPException(status_code=404, detail={'code': 'SEMANTIC_ANALYSIS_NOT_FOUND'})
        try:
            semantic = __import__('json').loads(cache.read_text(encoding='utf-8'))
            value = _service().adapt(semantic, payload.model_dump(exclude={'semanticAnalysisId'}))
            return {'semanticAnalysisId': payload.semanticAnalysisId, 'adaptedStory': value}
        except ComicAiError as exc:
            _ai_error(exc)

    @router.post('/generate-episode')
    def generate_episode(payload: ComicEpisodeRequest):
        try:
            return {'episode': _service().episode(payload.adaptedStory, payload.settings)}
        except ComicAiError as exc:
            _ai_error(exc)

    @router.post('/draft')
    def generate_draft(payload: ComicDraftRequest):
        path = _assert_registered(payload.token)
        total, pages = _source_pages(path, payload.startPage, payload.endPage)
        if not pages:
            raise HTTPException(status_code=422, detail='comic_source_has_no_pages')
        shots = []
        for index in range(payload.shotCount):
            source = pages[min(index * len(pages) // payload.shotCount, len(pages) - 1)]
            source_text = _first_sentence(source['text'])
            shots.append({
                'id': index + 1,
                'title': f'镜头 {index + 1:02d}',
                'sourcePage': source['page'],
                'duration': 5,
                'sourceText': source_text,
                'english': source_text if re.search(r'[A-Za-z]', source_text) else '',
                'chinese': '',
                'imagePrompt': f'Use comic page {source["page"]} as the visual reference. Preserve the original characters, clothing, props and setting.',
                'videoPrompt': f'Animate the scene from comic page {source["page"]} with restrained natural motion and consistent characters.',
                'negativePrompt': 'character drift, extra limbs, duplicated props, text artifacts, watermark',
                'sourcePages': [source['page']],
                'dialogueSource': 'source' if source_text else 'none',
            })

        episode_shots = []
        for shot in shots:
            source_text = shot.pop('sourceText')
            episode_shots.append({**shot, 'speaker': None, 'sourceEvidence': [{'sourcePage': shot['sourcePage'], 'evidence': source_text}]})

        provider = get_comic_ai_provider()
        return {
            'generationMode': 'source-scaffold',
            'requiresAiEnrichment': True,
            'provider': {'name': provider.name, 'enabled': provider.enabled},
            'episode': {
                'title': payload.title or path.stem,
                'level': payload.level,
                'age': payload.audience,
                'duration': payload.duration,
                'style': payload.style,
                'audience': payload.audience,
                'language': payload.language,
                'aspectRatio': payload.aspectRatio,
                'adaptation': {
                    'fidelity': payload.fidelity, 'strength': payload.adaptationStrength,
                    'educationalGoal': payload.educationalGoal,
                    'preserveCharacterNames': payload.preserveCharacterNames,
                    'preserveDialogues': payload.preserveDialogues,
                },
                'characters': [],
                'characterDefinitions': [],
                'scenes': [],
                'learningObjectives': [payload.educationalGoal] if payload.educationalGoal else [],
                'source': {
                    'type': 'comic',
                    'fileToken': payload.token,
                    'name': path.name,
                    'pages': [item['page'] for item in pages],
                },
                'shots': episode_shots,
            },
            'message': '已生成可编辑的 Episode/Shot 结构草稿。对白翻译、角色识别和剧情改编仍需 AI 语义增强。',
        }

    return router
