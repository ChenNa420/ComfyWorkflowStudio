from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .models import AdaptationContext, AdaptationPlan, AdaptedStoryDraft

ADAPT_SCHEMA_VERSION = '1h4c-v1'
ADAPT_PROMPT_VERSION = '1h4c-p1'


def _clean(value: Any) -> str:
    return ' '.join(str(value or '').split())


def _trim(value: Any, limit: int = 180) -> str:
    text = _clean(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + '…'


def _tokens(value: Any) -> set[str]:
    return {x.lower() for x in _clean(value).replace('-', ' ').split() if len(x) > 2}


def _semantic_core(semantic: dict[str, Any]) -> dict[str, Any]:
    keys = ('characters', 'scenes', 'dialogues', 'plotEvents', 'visualStyle', 'props', 'locations', 'storySummary', 'warnings', 'needsReview', 'source')
    return {key: semantic.get(key) for key in keys}


def semantic_hash(semantic: dict[str, Any]) -> str:
    raw = json.dumps(_semantic_core(semantic), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def adaptation_cache_key(semantic: dict[str, Any], model: str, settings: dict[str, Any]) -> str:
    payload = {
        'semanticHash': semantic_hash(semantic),
        'model': model,
        'schemaVersion': ADAPT_SCHEMA_VERSION,
        'promptVersion': ADAPT_PROMPT_VERSION,
        'audience': settings.get('audience'),
        'level': settings.get('level'),
        'fidelity': settings.get('fidelity'),
        'shotCount': settings.get('shotCount'),
        'autoShotCount': bool(settings.get('autoShotCount', False)),
        'style': settings.get('style'),
        'language': settings.get('language'),
        'preserveCharacterNames': settings.get('preserveCharacterNames'),
        'preserveCorePlot': settings.get('preserveCorePlot'),
        'preserveDialogue': settings.get('preserveDialogue'),
        'educationGoals': settings.get('educationGoals', []),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:32]


def _add_ref(refs: list[dict[str, Any]], restore: dict[str, dict[str, Any]], record_refs: dict[str, list[str]],
             key: str, page: int, kind: str, source_id: str, evidence: str) -> None:
    evidence_id = f'E{len(refs) + 1:03d}'
    refs.append({'id': evidence_id, 'sourcePage': page, 'kind': kind, 'sourceId': source_id})
    restore[evidence_id] = {'sourcePage': page, 'evidence': evidence or f'{kind} on source page {page}'}
    record_refs.setdefault(key, []).append(evidence_id)


def build_evidence_catalog(semantic: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[str]]]:
    refs: list[dict[str, Any]] = []
    restore: dict[str, dict[str, Any]] = {}
    record_refs: dict[str, list[str]] = {}
    for index, item in enumerate(semantic.get('dialogues', [])):
        _add_ref(refs, restore, record_refs, f'dialogue:{index}', int(item.get('page') or 1), 'dialogue',
                 f'dialogue-{index + 1}', _clean(item.get('evidence')) or _clean(item.get('text')))
    for kind, key_name in (('visual_event', 'plotEvents'), ('scene', 'scenes'), ('character', 'characters')):
        for index, item in enumerate(semantic.get(key_name, [])):
            evidence_values = item.get('evidence', []) or []
            if not evidence_values:
                pages = item.get('pages', []) or [item.get('firstSeenPage') or 1]
                evidence_values = [{'sourcePage': pages[0], 'evidence': _clean(item.get('action') or item.get('description') or item.get('name'))}]
            for ev_index, evidence in enumerate(evidence_values):
                page = int(evidence.get('sourcePage') or (item.get('pages') or [item.get('firstSeenPage') or 1])[0])
                _add_ref(refs, restore, record_refs, f'{key_name}:{index}', page, kind,
                         f'{item.get("id") or key_name + "-" + str(index + 1)}:{ev_index + 1}', _clean(evidence.get('evidence')))
    return refs, restore, record_refs


def _scene_for_page(scenes: list[dict[str, Any]], page: int) -> str | None:
    match = next((item for item in scenes if page in (item.get('pages') or [])), None)
    return _clean(match.get('id')) if match else None


def _narrative_tokens(semantic: dict[str, Any]) -> set[str]:
    summary = semantic.get('storySummary') or {}
    values = [summary.get(key, '') for key in ('premise', 'beginning', 'middle', 'ending', 'conflict', 'resolution')]
    for item in semantic.get('plotEvents', []):
        values.extend([item.get('action', ''), item.get('cause', ''), item.get('result', '')])
    return _tokens(' '.join(_clean(value) for value in values))


def _compress_dialogues(semantic: dict[str, Any], record_refs: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scenes = semantic.get('scenes', [])
    narrative = _narrative_tokens(semantic)
    unique: list[tuple[int, dict[str, Any]]] = []
    seen: set[tuple[int, str, str]] = set()
    for index, item in enumerate(semantic.get('dialogues', [])):
        page = int(item.get('page') or 1)
        speaker = _clean(item.get('speakerId')) or 'unknown'
        text = _clean(item.get('text'))
        key = (page, text.lower(), speaker.lower())
        if not text or key in seen:
            continue
        seen.add(key); unique.append((index, item))
    by_page: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for pair in unique:
        by_page.setdefault(int(pair[1].get('page') or 1), []).append(pair)
    selected: set[int] = set()
    event_pages = {page for item in semantic.get('plotEvents', []) for page in item.get('pages', [])}
    for page, values in by_page.items():
        scored = []
        for position, (index, item) in enumerate(values):
            score = len(_tokens(item.get('text')) & narrative) * 2
            score += 3 if item.get('speakerId') else 0
            score += 2 if position in {0, len(values) - 1} else 0
            score += 2 if page in event_pages else 0
            score += 1 if any(mark in _clean(item.get('text')) for mark in ('?', '!', '？', '！')) else 0
            scored.append((score, -position, index))
        selected.update(index for _, _, index in sorted(scored, reverse=True)[:4])
    key_dialogues: list[dict[str, Any]] = []
    omitted_by_page: dict[int, int] = {}
    for index, item in unique:
        page = int(item.get('page') or 1)
        if index not in selected:
            omitted_by_page[page] = omitted_by_page.get(page, 0) + 1
            continue
        speaker = _clean(item.get('speakerId')) or 'unknown'
        key_dialogues.append({
            'id': f'D{index + 1:03d}', 'sourcePage': page, 'sceneId': _scene_for_page(scenes, page),
            'speaker': speaker, 'text': _trim(item.get('text'), 180), 'dialogueSource': 'source',
            'sourceEvidenceIds': record_refs.get(f'dialogue:{index}', []),
        })
    summaries = [{
        'sourcePage': page, 'sceneId': _scene_for_page(scenes, page), 'omittedCount': count,
        'summary': f'{count} additional source dialogue lines remain in SemanticAnalysis and were omitted from the model context.',
    } for page, count in sorted(omitted_by_page.items()) if count]
    return key_dialogues, summaries


def _meaningful(value: Any) -> bool:
    text = _clean(value).lower()
    return bool(text and text not in {'unknown', 'none', 'null'} and not text.startswith('character '))


def _classify_characters(semantic: dict[str, Any], record_refs: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dialogue_ids = {item.get('speakerId') for item in semantic.get('dialogues', []) if item.get('speakerId')}
    event_ids = {cid for item in semantic.get('plotEvents', []) for cid in item.get('characters', [])}
    scene_ids = {cid for item in semantic.get('scenes', []) for cid in item.get('characters', [])}
    values: list[dict[str, Any]] = []
    for index, item in enumerate(semantic.get('characters', [])):
        cid = _clean(item.get('id'))
        pages = sorted({int(page) for page in item.get('pages', []) if isinstance(page, int) and page > 0})
        score = (4 if cid in dialogue_ids else 0) + (4 if cid in event_ids else 0) + (2 if cid in scene_ids else 0)
        score += 1 if len(pages) > 1 else 0
        score += 1 if _meaningful(item.get('name')) or _meaningful(item.get('role')) else 0
        score += 1 if float(item.get('confidence') or 0) >= .6 else 0
        classification = 'main' if score >= 4 else 'supporting' if score >= 1 else 'background'
        summary_parts = [value for value in (_clean(item.get('role')), _clean(item.get('description')), _clean(item.get('appearance')), _clean(item.get('clothing'))) if _meaningful(value)]
        values.append({
            'id': cid, 'name': _clean(item.get('name')) or 'unknown', 'role': _clean(item.get('role')) or 'unknown',
            'classification': classification, 'pages': pages, 'summary': _trim('; '.join(summary_parts), 180),
            'confidence': float(item.get('confidence') or 0), 'needsReview': bool(item.get('needsReview')),
            'sourceEvidenceIds': record_refs.get(f'characters:{index}', []), '_score': score,
        })
    if values and not any(item['classification'] == 'main' for item in values):
        promotable = [item for item in values if item['classification'] == 'supporting']
        promotable.sort(key=lambda item: (-item['_score'], (item['pages'] or [9999])[0], item['id']))
        for item in promotable[:4]: item['classification'] = 'main'
    compact = []
    background = []
    for item in values:
        item.pop('_score', None)
        if item['classification'] == 'background':
            item['summary'] = ''
            background.append(item)
        else:
            compact.append(item)
    return compact, background


def _refs_for_pages(refs: list[dict[str, Any]], pages: list[int], limit: int = 6) -> list[str]:
    allowed = set(pages)
    return [item['id'] for item in refs if item['sourcePage'] in allowed][:limit]


def _context_story_beats(semantic: dict[str, Any], refs: list[dict[str, Any]], source_pages: list[int]) -> list[dict[str, Any]]:
    summary = semantic.get('storySummary') or {}
    beats: list[dict[str, Any]] = []
    positions = [('beginning', source_pages[:1]), ('middle', source_pages[1:-1] or source_pages[:1]), ('ending', source_pages[-1:])]
    for label, pages in positions:
        text = _clean(summary.get(label))
        if text:
            beats.append({'id': f'context-{label}', 'summary': _trim(text, 220), 'sourcePages': pages,
                          'sourceEvidenceIds': _refs_for_pages(refs, pages)})
    for index, item in enumerate(semantic.get('plotEvents', [])):
        pages = [int(page) for page in item.get('pages', []) if isinstance(page, int) and page > 0] or source_pages[:1]
        beats.append({'id': f'context-event-{index + 1}', 'summary': _trim(item.get('action'), 220),
                      'sourcePages': pages, 'sourceEvidenceIds': _refs_for_pages(refs, pages)})
    return beats


def build_adaptation_context(semantic: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    source_pages = [int(page) for page in semantic.get('source', {}).get('pages', []) if isinstance(page, int) and page > 0]
    refs, restore, record_refs = build_evidence_catalog(semantic)
    key_dialogues, dialogue_summary = _compress_dialogues(semantic, record_refs)
    characters, background = _classify_characters(semantic, record_refs)
    scenes = [{
        'id': _clean(item.get('id')), 'location': _clean(item.get('location')) or 'unknown',
        'timeOfDay': _clean(item.get('timeOfDay')) or 'unknown', 'description': _trim(item.get('description'), 180),
        'pages': item.get('pages', []), 'characters': item.get('characters', []), 'mood': _clean(item.get('mood')) or 'unknown',
    } for item in semantic.get('scenes', [])]
    events = [{
        'id': _clean(item.get('id')), 'pages': item.get('pages', []), 'characters': item.get('characters', []),
        'action': _trim(item.get('action'), 220), 'cause': _trim(item.get('cause'), 120), 'result': _trim(item.get('result'), 120),
        'sourceEvidenceIds': record_refs.get(f'plotEvents:{index}', []),
    } for index, item in enumerate(semantic.get('plotEvents', []))]
    story = semantic.get('storySummary') or {}
    context = AdaptationContext.model_validate({
        'sourcePages': source_pages, 'tone': _clean(story.get('tone')) or 'unknown', 'premise': _trim(story.get('premise'), 260),
        'characters': characters, 'backgroundCharacters': background, 'scenes': scenes,
        'storyBeats': _context_story_beats(semantic, refs, source_pages), 'keyDialogues': key_dialogues,
        'dialogueSummary': dialogue_summary, 'plotEvents': events, 'sourceEvidence': refs,
    }).model_dump()
    stats = {
        'dialogues': len(semantic.get('dialogues', [])), 'keyDialogues': len(key_dialogues),
        'characters': len(semantic.get('characters', [])), 'mainCharacters': sum(x['classification'] == 'main' for x in characters),
        'supportingCharacters': sum(x['classification'] == 'supporting' for x in characters), 'backgroundCharacters': len(background),
        'evidence': len(refs), 'compactEvidenceRefs': len(refs),
    }
    return context, restore, stats


def recommended_shot_count(plan: dict[str, Any], context: dict[str, Any], settings: dict[str, Any]) -> int:
    if not bool(settings.get('autoShotCount', False)):
        try:
            fixed = int(settings.get('shotCount') or 0)
        except (TypeError, ValueError):
            fixed = 0
        if fixed > 0:
            return max(1, min(12, fixed))
    suggested = plan.get('recommendedShotCount')
    if isinstance(suggested, int) and 1 <= suggested <= 12:
        return suggested
    beats = max(1, len(plan.get('beats', [])))
    scenes = len(context.get('scenes', []))
    dialogues = len(context.get('keyDialogues', []))
    events = len(context.get('plotEvents', []))
    count = max(beats, min(12, scenes or 1))
    if dialogues > max(4, beats * 3):
        count += 1
    if events > max(4, beats * 2):
        count += 1
    return max(4, min(12, count))


def complete_adaptation_plan(plan: dict[str, Any], context: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    value = dict(plan)
    if not value.get('mainCharacters'):
        value['mainCharacters'] = [
            item['id'] for item in context.get('characters', [])
            if item.get('classification') == 'main'
        ][:4]
    if not value.get('sourceEvidenceIds'):
        refs: list[str] = []
        for beat in value.get('beats', []):
            refs.extend(beat.get('sourceEvidenceIds', []))
        value['sourceEvidenceIds'] = list(dict.fromkeys(refs))
    value['narrativeType'] = _clean(value.get('narrativeType')) or 'narrative_story'
    return AdaptationPlan.model_validate(value).model_dump()


def validate_plan_references(plan: dict[str, Any], context: dict[str, Any]) -> None:
    evidence_ids = {item['id'] for item in context.get('sourceEvidence', [])}
    character_ids = {item['id'] for item in context.get('characters', []) + context.get('backgroundCharacters', [])}
    dialogue_ids = {item['id'] for item in context.get('keyDialogues', [])}
    if any(item not in evidence_ids for item in plan.get('sourceEvidenceIds', [])):
        raise ValueError('ADAPT_PLAN_UNKNOWN_EVIDENCE_ID')
    if any(item not in character_ids for item in plan.get('mainCharacters', [])):
        raise ValueError('ADAPT_PLAN_UNKNOWN_CHARACTER_ID')
    if any(item not in dialogue_ids for item in plan.get('unassignedDialogue', [])):
        raise ValueError('ADAPT_PLAN_UNKNOWN_DIALOGUE_ID')
    for beat in plan.get('beats', []):
        if any(item not in evidence_ids for item in beat.get('sourceEvidenceIds', [])):
            raise ValueError('ADAPT_PLAN_UNKNOWN_EVIDENCE_ID')


def complete_adapted_story_draft(raw: dict[str, Any], plan: dict[str, Any], context: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    value = dict(raw or {})
    plan_beats = {item['id']: item for item in plan.get('beats', [])}
    raw_beats = {item.get('id'): item for item in value.get('storyBeats', []) if isinstance(item, dict) and item.get('id')}
    extra_ids = [beat_id for beat_id in raw_beats if beat_id not in plan_beats]
    if extra_ids:
        raise ValueError('ADAPT_STORY_UNKNOWN_BEAT_ID')
    completed = []
    inserted = []
    for beat_id, source in plan_beats.items():
        if beat_id in raw_beats:
            completed.append(raw_beats[beat_id])
        else:
            completed.append(dict(source))
            inserted.append(beat_id)
    value['storyBeats'] = completed
    if not value.get('sourceEvidenceIds'):
        value['sourceEvidenceIds'] = list(dict.fromkeys(plan.get('sourceEvidenceIds', [])))
    if not value.get('learningGoals'):
        value['learningGoals'] = list(settings.get('educationGoals', []))
    notes = list(value.get('adaptationNotes', []))
    if inserted:
        notes.append('Restored omitted plan beats deterministically: ' + ', '.join(inserted))
    value['adaptationNotes'] = notes
    return AdaptedStoryDraft.model_validate(value).model_dump()


def validate_draft_references(draft: dict[str, Any], context: dict[str, Any]) -> None:
    evidence_ids = {item['id'] for item in context.get('sourceEvidence', [])}
    character_ids = {item['id'] for item in context.get('characters', []) + context.get('backgroundCharacters', [])}
    if any(item not in evidence_ids for item in draft.get('sourceEvidenceIds', [])):
        raise ValueError('ADAPT_STORY_UNKNOWN_EVIDENCE_ID')
    for beat in draft.get('storyBeats', []):
        if any(item not in evidence_ids for item in beat.get('sourceEvidenceIds', [])):
            raise ValueError('ADAPT_STORY_UNKNOWN_EVIDENCE_ID')
    for character in draft.get('characters', []):
        if isinstance(character, dict) and character.get('id') and character['id'] not in character_ids:
            raise ValueError('ADAPT_STORY_UNKNOWN_CHARACTER_ID')


def restore_source_evidence(ids: list[str], restore: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for evidence_id in ids:
        if evidence_id in seen or evidence_id not in restore:
            continue
        seen.add(evidence_id); result.append(dict(restore[evidence_id]))
    return result


def read_cached(path: Path, model: type[AdaptationContext] | type[AdaptationPlan] | type[AdaptedStoryDraft]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return model.model_validate_json(path.read_text(encoding='utf-8')).model_dump()
    except (OSError, ValueError):
        return None


def write_cached(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def final_story_from_draft(draft: dict[str, Any], restore: dict[str, dict[str, Any]], plan: dict[str, Any] | None = None, effective_shot_count: int | None = None) -> dict[str, Any]:
    evidence_ids = list(draft.get('sourceEvidenceIds', []))
    for beat in draft.get('storyBeats', []):
        evidence_ids.extend(beat.get('sourceEvidenceIds', []))
    plan = plan or {}
    return {
        'title': draft['title'], 'logline': draft['logline'], 'summary': draft['summary'],
        'characters': draft.get('characters', []), 'scenes': draft.get('scenes', []),
        'storyBeats': draft.get('storyBeats', []), 'ending': draft['ending'],
        'learningGoals': draft.get('learningGoals', []),
        'sourceEvidence': restore_source_evidence(evidence_ids, restore),
        'adaptationNotes': draft.get('adaptationNotes', []),
        'narrativeType': plan.get('narrativeType', 'narrative_story'),
        'recommendedShotCount': effective_shot_count or plan.get('recommendedShotCount'),
    }
