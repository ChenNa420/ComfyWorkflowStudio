from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from .models import PageDialogueResult, PageVisualResult, SemanticAnalysis, SCHEMA_VERSION

STRATEGY = 'pagewise-fusion'


def _clean(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _known_name(value: Any) -> str | None:
    name = _clean(value)
    return None if name.lower() in {'', 'unknown', 'null', 'none'} else name


def _tokens(value: Any) -> set[str]:
    return {x for x in re.findall(r'[a-z0-9]+', _clean(value).lower()) if len(x) > 2 and x not in {'unknown', 'none'}}


def _character_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_name, right_name = _known_name(left.get('name')), _known_name(right.get('name'))
    if left_name and right_name:
        return left_name.casefold() == right_name.casefold()
    matches = 0
    for cue in ('appearance', 'clothing', 'bodyType', 'hairOrFur'):
        a, b = _tokens(left.get(cue)), _tokens(right.get(cue))
        if a and b and len(a & b) / max(1, min(len(a), len(b))) >= .6:
            matches += 1
    a, b = _tokens(' '.join(left.get('accessories', []))), _tokens(' '.join(right.get('accessories', [])))
    if a and b and a & b:
        matches += 1
    return matches >= 2


def _evidence(page: int, kind: str, description: str) -> dict[str, Any]:
    return {'sourcePage': page, 'evidenceType': kind, 'evidence': description, 'systemGrounded': True}


def _cache_key(fingerprint: dict[str, Any], page: int, model: str, profile: str, purpose: str) -> str:
    value = {**fingerprint, 'page': page, 'model': model, 'schema': SCHEMA_VERSION,
             'strategy': STRATEGY, 'imageProfile': profile, 'purpose': purpose}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _read_cache(path: Path, validator: Callable[[dict[str, Any]], Any]) -> dict[str, Any] | None:
    try:
        return validator(json.loads(path.read_text(encoding='utf-8'))).model_dump()
    except (OSError, json.JSONDecodeError, ValidationError, ValueError):
        return None


def _write_cache(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def _summary(events: list[dict[str, Any]], dialogues: list[dict[str, Any]]) -> dict[str, Any]:
    facts = [_clean(x.get('action')) for x in events if _clean(x.get('action'))]
    if not facts:
        facts = [_clean(x.get('text')) for x in dialogues if _clean(x.get('text'))]
    if not facts:
        return {'titleGuess': 'unknown', 'premise': '', 'beginning': '', 'middle': '', 'ending': '',
                'conflict': 'unknown', 'resolution': 'unknown', 'themes': [], 'tone': 'unknown'}
    return {'titleGuess': 'unknown', 'premise': ' '.join(facts[:3])[:600], 'beginning': facts[0][:280],
            'middle': facts[len(facts) // 2][:280], 'ending': facts[-1][:280], 'conflict': 'unknown',
            'resolution': 'unknown', 'themes': [], 'tone': 'unknown'}


def fuse_page_results(page_results: list[dict[str, Any]]) -> dict[str, Any]:
    characters: list[dict[str, Any]] = []
    temp_to_stable: dict[tuple[int, str], str] = {}
    warnings: list[str] = []
    for page_result in page_results:
        page, visual = page_result['page'], page_result.get('visual') or {}
        for incoming in visual.get('characters', []):
            found = next((item for item in characters if _character_match(item, incoming)), None)
            temporary_id = _clean(incoming.get('temporaryId'))
            if found is None:
                key = f'character_{len(characters) + 1:02d}'
                name = _known_name(incoming.get('name')) or f'Character {len(characters) + 1:02d}'
                found = {'id': key, 'name': name, 'aliases': [], 'description': _clean(incoming.get('roleHint')),
                         'appearance': _clean(incoming.get('appearance')), 'clothing': _clean(incoming.get('clothing')),
                         'bodyType': _clean(incoming.get('bodyType')) or 'unknown',
                         'hairOrFur': _clean(incoming.get('hairOrFur')) or 'unknown',
                         'accessories': incoming.get('accessories', []), 'personality': 'unknown',
                         'prompt': ', '.join(x for x in [_clean(incoming.get('appearance')), _clean(incoming.get('clothing')),
                                                       _clean(incoming.get('bodyType')), _clean(incoming.get('hairOrFur'))] if x and x != 'unknown'),
                         'negativePrompt': 'identity drift, inconsistent clothing, extra limbs',
                         'role': _clean(incoming.get('roleHint')) or 'unknown', 'firstSeenPage': page, 'pages': [page],
                         'confidence': float(incoming.get('confidence', 0)),
                         'evidence': [_evidence(page, 'visual_character', 'character visible on selected comic page')],
                         'needsReview': bool(incoming.get('needsReview')) or not _known_name(incoming.get('name'))}
                characters.append(found)
            else:
                found['pages'] = sorted(set(found['pages'] + [page]))
                found['confidence'] = max(found['confidence'], float(incoming.get('confidence', 0)))
                found['evidence'].append(_evidence(page, 'visual_character', 'matching character visible on selected comic page'))
                if _known_name(incoming.get('name')) and found['name'].startswith('Character '):
                    found['name'] = _known_name(incoming.get('name')); found['needsReview'] = False
            if temporary_id:
                temp_to_stable[(page, temporary_id)] = found['id']

    dialogues: list[dict[str, Any]] = []
    scenes: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    props: list[dict[str, Any]] = []
    for page_result in page_results:
        page = page_result['page']
        dialogue, visual = page_result.get('dialogue') or {}, page_result.get('visual') or {}
        warnings.extend(dialogue.get('warnings', [])); warnings.extend(visual.get('warnings', [])); warnings.extend(page_result.get('warnings', []))
        for item in dialogue.get('dialogues', []):
            temporary_id = _clean(item.get('speakerTemporaryId'))
            speaker = temp_to_stable.get((page, temporary_id)) if temporary_id else None
            if not speaker and _clean(item.get('speakerDescription')):
                description_tokens = _tokens(item.get('speakerDescription'))
                candidates = [character for character in characters if page in character['pages'] and
                              description_tokens & _tokens(' '.join([character['appearance'], character['clothing'], character['bodyType'], character['hairOrFur']]))]
                if len(candidates) == 1:
                    speaker = candidates[0]['id']
            dialogues.append({'page': page, 'speakerId': speaker, 'text': _clean(item.get('text')),
                              'language': 'unknown', 'confidence': float(item.get('confidence', 0)),
                              'evidence': 'transcribed from visible speech bubble or caption',
                              'evidenceType': 'speech_bubble', 'systemGrounded': True,
                              'speakerResolution': 'resolved' if speaker else 'unknown',
                              'speakerDescription': _clean(item.get('speakerDescription')),
                              'bubblePosition': _clean(item.get('bubblePosition')) or 'unknown',
                              'needsReview': bool(item.get('needsReview'))})
        scene = visual.get('scene')
        if scene:
            location = _clean(scene.get('location')) or 'unknown'
            previous = scenes[-1] if scenes else None
            same_location = previous and location != 'unknown' and previous['location'].casefold() == location.casefold()
            if same_location:
                previous['pages'].append(page)
                previous['description'] = ' '.join(x for x in [previous['description'], _clean(scene.get('description'))] if x)
                previous['evidence'].append(_evidence(page, 'visual_scene', 'scene visible on selected comic page'))
            else:
                scenes.append({'id': f'scene_{len(scenes) + 1:02d}', 'location': location,
                               'timeOfDay': _clean(scene.get('timeOfDay')) or 'unknown',
                               'description': _clean(scene.get('description')), 'pages': [page], 'characters': [],
                               'props': [], 'mood': _clean(scene.get('mood')) or 'unknown',
                               'confidence': float(scene.get('confidence', 0)),
                               'evidence': [_evidence(page, 'visual_scene', 'scene visible on selected comic page')]})
        page_events = visual.get('plotEvents', [])
        if not page_events and scene and _clean(scene.get('description')):
            page_events = [{'action': _clean(scene.get('description')), 'characterTemporaryIds': [],
                            'confidence': min(.45, float(scene.get('confidence', 0))), 'needsReview': True}]
            warnings.append(f'PAGE_{page}_EVENT_DERIVED_FROM_SCENE')
        for item in page_events:
            ids = [temp_to_stable[(page, value)] for value in item.get('characterTemporaryIds', []) if (page, value) in temp_to_stable]
            events.append({'id': f'event_{len(events) + 1:02d}', 'pages': [page], 'characters': ids,
                           'action': _clean(item.get('action')), 'cause': 'unknown', 'result': 'unknown',
                           'importance': 'supporting', 'confidence': float(item.get('confidence', 0)),
                           'evidence': [_evidence(page, 'visual_action', 'action visible on selected comic page')]})
        for item in visual.get('props', []):
            owner = temp_to_stable.get((page, _clean(item.get('ownerTemporaryId'))))
            props.append({'id': f'prop_{len(props) + 1:02d}', 'name': _clean(item.get('name')) or 'unknown',
                          'description': _clean(item.get('description')), 'pages': [page],
                          'ownerCharacterId': owner, 'confidence': float(item.get('confidence', 0))})
    locations = []
    for scene in scenes:
        if scene['location'] != 'unknown' and not any(x['name'].casefold() == scene['location'].casefold() for x in locations):
            locations.append({'id': f'location_{len(locations) + 1:02d}', 'name': scene['location'],
                              'description': scene['description'], 'pages': scene['pages'], 'confidence': scene['confidence']})
    value = {'characters': characters, 'scenes': scenes, 'dialogues': dialogues, 'plotEvents': events,
             'visualStyle': {}, 'props': props, 'locations': locations, 'storySummary': _summary(events, dialogues),
             'warnings': list(dict.fromkeys(warnings)), 'needsReview': bool(warnings) or any(x['needsReview'] for x in characters)}
    return SemanticAnalysis.model_validate(value).model_dump()


def analyze_pagewise(provider: Any, path: Path, pages: list[dict[str, Any]], fingerprint: dict[str, Any],
                     model: str, profile: str, edge: int, cache_dir: Path, force_refresh: bool,
                     render_page: Callable[..., tuple[bytes, dict[str, Any]]]) -> tuple[dict[str, Any], dict[str, Any]]:
    page_results: list[dict[str, Any]] = []
    page_metrics: list[dict[str, Any]] = []
    render_metrics: list[dict[str, Any]] = []
    total_requests = 0
    started = time.monotonic()
    for source in pages:
        page = source['page']
        image, image_meta = render_page(path, page, edge)
        render_metrics.append({**image_meta, 'page': page})
        request_page = {**source, 'image': image, 'imageMeta': image_meta}
        current: dict[str, Any] = {'page': page, 'warnings': []}
        metric = {'page': page, 'dialogueCount': 0, 'characterCount': 0, 'sceneCount': 0, 'eventCount': 0,
                  'dialogueDuration': 0.0, 'visualDuration': 0.0, 'dialogueCacheHit': False, 'visualCacheHit': False}
        for purpose, method, validator in (
            ('dialogue', provider.analyze_page_dialogue, PageDialogueResult.model_validate),
            ('visual', provider.analyze_page_visual, PageVisualResult.model_validate),
        ):
            target = cache_dir / 'pages' / f'{_cache_key(fingerprint, page, model, profile, purpose)}.json'
            value = None if force_refresh else _read_cache(target, validator)
            if value is not None:
                metric[f'{purpose}CacheHit'] = True
            else:
                pass_started = time.monotonic()
                try:
                    total_requests += 1; raw = method(request_page)
                    raw.pop('_requestRetries', None); raw['page'] = page
                    value = validator(raw).model_dump(); _write_cache(target, value)
                except Exception as exc:
                    current['warnings'].append(f'PAGE_{page}_{purpose.upper()}_ANALYSIS_FAILED')
                    current[f'{purpose}Error'] = type(exc).__name__
                metric[f'{purpose}Duration'] = round(time.monotonic() - pass_started, 3)
            if value is not None:
                current[purpose] = value
        metric['dialogueCount'] = len((current.get('dialogue') or {}).get('dialogues', []))
        visual = current.get('visual') or {}
        metric['characterCount'] = len(visual.get('characters', []))
        metric['sceneCount'] = int(bool(visual.get('scene')))
        metric['eventCount'] = len(visual.get('plotEvents', []))
        metric['dialogueError'] = current.get('dialogueError')
        metric['visualError'] = current.get('visualError')
        page_results.append(current); page_metrics.append(metric)
    fusion_started = time.monotonic(); fused = fuse_page_results(page_results)
    return fused, {'pageMetrics': page_metrics, 'renderMetrics': render_metrics, 'totalRequests': total_requests,
                   'fusionDuration': round(time.monotonic() - fusion_started, 3),
                   'totalDuration': round(time.monotonic() - started, 3)}
