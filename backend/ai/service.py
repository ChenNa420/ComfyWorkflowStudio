from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import fitz
from pydantic import ValidationError

from .models import SCHEMA_VERSION, SemanticAnalysis


ERROR_CODES = {
    'AI_PROVIDER_DISABLED', 'AI_PROVIDER_UNAVAILABLE', 'AI_MODEL_NOT_CONFIGURED',
    'AI_MODEL_VISION_UNSUPPORTED', 'AI_RESPONSE_INVALID', 'AI_REQUEST_TIMEOUT',
    'AI_CONTEXT_TOO_LARGE',
}


class ComicAiError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code if code in ERROR_CODES else 'AI_PROVIDER_UNAVAILABLE'
        super().__init__(message or self.code)


def _file_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'sha256': digest.hexdigest(), 'size': stat.st_size, 'mtimeNs': stat.st_mtime_ns}


def _render_page(path: Path, page_number: int) -> bytes:
    if path.suffix.lower() == '.pdf':
        with fitz.open(path) as doc:
            page = doc.load_page(page_number - 1)
            scale = min(1.6, 1600 / max(page.rect.width, page.rect.height))
            return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes('jpeg', jpg_quality=78)
    if path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'} and page_number == 1:
        return path.read_bytes()
    # Archives are already safely previewed by the API; Phase 1H-3 keeps the same
    # source registry and adds archive image extraction in one bounded operation.
    import zipfile
    with zipfile.ZipFile(path) as archive:
        names = sorted(n for n in archive.namelist() if Path(n).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'})
        return archive.read(names[page_number - 1])


def _context(result: dict[str, Any]) -> dict[str, Any]:
    return {
        'knownCharacters': [{'id': c.get('id'), 'name': c.get('name'), 'appearance': c.get('appearance'), 'clothing': c.get('clothing')} for c in result.get('characters', [])],
        'currentLocation': (result.get('scenes') or [{}])[-1].get('location'),
        'lastPlotEvent': (result.get('plotEvents') or [{}])[-1].get('action'),
    }


def _same_character(left: dict[str, Any], right: dict[str, Any]) -> bool:
    ln, rn = str(left.get('name', '')).lower(), str(right.get('name', '')).lower()
    if ln not in {'', 'unknown'} and not ln.startswith('character-') and ln == rn:
        return True
    # Conservative anonymous merge: require two independent, non-empty visual cues.
    cues = ('appearance', 'clothing')
    return sum(bool(left.get(c)) and str(left.get(c)).lower() == str(right.get(c)).lower() for c in cues) == 2


def merge_batches(batches: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {'characters': [], 'scenes': [], 'dialogues': [], 'plotEvents': [], 'props': [], 'locations': [], 'warnings': []}
    styles: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    id_map: dict[str, str] = {}
    for batch in batches:
        for incoming in batch.get('characters', []):
            found = next((c for c in merged['characters'] if _same_character(c, incoming)), None)
            if found:
                id_map[incoming['id']] = found['id']
                found['pages'] = sorted(set(found.get('pages', []) + incoming.get('pages', [])))
                found['evidence'] = found.get('evidence', []) + incoming.get('evidence', [])
                found['confidence'] = max(float(found.get('confidence', 0)), float(incoming.get('confidence', 0)))
            else:
                copied = dict(incoming)
                copied['id'] = f"character-{len(merged['characters']) + 1:02d}"
                id_map[incoming['id']] = copied['id']
                merged['characters'].append(copied)
        for key in ('scenes', 'dialogues', 'plotEvents', 'props', 'locations', 'warnings'):
            values = batch.get(key, [])
            for item in values:
                if isinstance(item, dict):
                    item = dict(item)
                    if item.get('speakerId') in id_map: item['speakerId'] = id_map[item['speakerId']]
                    if item.get('ownerCharacterId') in id_map: item['ownerCharacterId'] = id_map[item['ownerCharacterId']]
                    if isinstance(item.get('characters'), list): item['characters'] = [id_map.get(x, x) for x in item['characters']]
                merged[key].append(item)
        if batch.get('visualStyle'): styles.append(batch['visualStyle'])
        if batch.get('storySummary'): summaries.append(batch['storySummary'])
    merged['visualStyle'] = styles[-1] if styles else {}
    merged['storySummary'] = summaries[-1] if summaries else {}
    merged['needsReview'] = any(bool(x.get('needsReview')) for x in batches) or any(c.get('needsReview') for c in merged['characters'])
    return merged


class ComicAiService:
    def __init__(self, provider: Any, cache_dir: Path):
        self.provider = provider
        self.cache_dir = cache_dir

    def status(self) -> dict[str, Any]:
        return self.provider.get_status()

    def analyze(self, path: Path, token: str, pages: list[dict[str, Any]], force_refresh: bool = False) -> dict[str, Any]:
        status = self.status()
        if not status['enabled']:
            raise ComicAiError('AI_PROVIDER_DISABLED')
        if not status['configured']:
            raise ComicAiError('AI_MODEL_NOT_CONFIGURED')
        if len(pages) > 12:
            raise ComicAiError('AI_CONTEXT_TOO_LARGE', 'A maximum of 12 pages may be analyzed at once')
        fingerprint = _file_fingerprint(path)
        key_input = {**fingerprint, 'pages': [p['page'] for p in pages], 'provider': status['provider'], 'model': status['model'], 'schema': SCHEMA_VERSION}
        analysis_id = hashlib.sha256(json.dumps(key_input, sort_keys=True).encode()).hexdigest()[:24]
        target = self.cache_dir / f'{analysis_id}.json'
        if target.is_file() and not force_refresh:
            result = json.loads(target.read_text(encoding='utf-8'))
            result['cacheHit'] = True
            return result
        results: list[dict[str, Any]] = []
        prior: dict[str, Any] = {}
        try:
            for offset in range(0, len(pages), 4):
                batch = []
                for page in pages[offset:offset + 4]:
                    batch.append({**page, 'image': _render_page(path, page['page'])})
                raw = self.provider.analyze_comic_pages(batch, prior)
                validated = SemanticAnalysis.validate_provider(raw).model_dump()
                results.append(validated)
                prior = _context(validated)
            merged = SemanticAnalysis.validate_provider(merge_batches(results)).model_dump()
        except TimeoutError as exc:
            raise ComicAiError('AI_REQUEST_TIMEOUT') from exc
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise ComicAiError('AI_RESPONSE_INVALID') from exc
        except ComicAiError:
            raise
        except RuntimeError as exc:
            raise ComicAiError(str(exc)) from exc
        result = {**merged, 'id': analysis_id,
                  'source': {'type': 'comic', 'name': path.name, 'fileToken': token, 'pages': [p['page'] for p in pages]},
                  'provider': status['provider'], 'model': status['model'], 'schemaVersion': SCHEMA_VERSION,
                  'cacheHit': False, 'batchCount': len(results)}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result

    def adapt(self, semantic: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        status = self.status()
        if not status['enabled']:
            raise ComicAiError('AI_PROVIDER_DISABLED')
        if not status['configured']:
            raise ComicAiError('AI_MODEL_NOT_CONFIGURED')
        try:
            result = self.provider.adapt_story(semantic, settings)
            if not isinstance(result, dict): raise ValueError()
            return result
        except TimeoutError as exc:
            raise ComicAiError('AI_REQUEST_TIMEOUT') from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise ComicAiError('AI_RESPONSE_INVALID') from exc
        except RuntimeError as exc:
            raise ComicAiError(str(exc)) from exc

    def episode(self, story: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        status = self.status()
        if not status['enabled']:
            raise ComicAiError('AI_PROVIDER_DISABLED')
        if not status['configured']:
            raise ComicAiError('AI_MODEL_NOT_CONFIGURED')
        try:
            value = self.provider.generate_episode(story, settings)
            if not isinstance(value, dict): raise ValueError()
            json.dumps(value)
            return value
        except (ValueError, TypeError) as exc:
            raise ComicAiError('AI_RESPONSE_INVALID') from exc
