from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import EpisodeShotPlan

EPISODE_PLAN_REVISION = '1h4c1-plan-v1'
EPISODE_SHOT_PROMPT_VERSION = '1h4c1-shot-p2'


def resolve_shot_count(story: dict[str, Any], settings: dict[str, Any]) -> int:
    if bool(settings.get('autoShotCount', False)):
        suggested = story.get('recommendedShotCount')
        if isinstance(suggested, int) and 4 <= suggested <= 12:
            return suggested
        beats = [item for item in story.get('storyBeats', []) if isinstance(item, dict)]
        evidence = len(story.get('sourceEvidence', []))
        return max(4, min(12, len(beats) + (1 if evidence > max(4, len(beats) * 2) else 0)))
    try:
        return max(1, min(12, int(settings.get('shotCount') or 6)))
    except (TypeError, ValueError):
        return 6


def _allocate_durations(total: Any, count: int) -> list[float]:
    try:
        target = float(total)
    except (TypeError, ValueError):
        target = count * 5.0
    target = max(count * 0.1, min(count * 10.0, target))
    units = max(count, int(round(target * 10)))
    base, extra = divmod(units, count)
    return [(base + (1 if index < extra else 0)) / 10 for index in range(count)]


def _beat_score(beat: dict[str, Any]) -> int:
    return len(str(beat.get('summary') or '')) + 30 * len(beat.get('sourcePages', [])) + 20 * len(beat.get('sourceEvidenceIds', []))


def _groups(beats: list[dict[str, Any]], count: int) -> list[list[dict[str, Any]]]:
    if count < len(beats):
        return [beats[index * len(beats) // count:(index + 1) * len(beats) // count] for index in range(count)]
    assignments = [1] * len(beats)
    for _ in range(count - len(beats)):
        choice = max(range(len(beats)), key=lambda index: (_beat_score(beats[index]) / assignments[index], -index))
        assignments[choice] += 1
    result: list[list[dict[str, Any]]] = []
    for beat, copies in zip(beats, assignments):
        result.extend([[beat]] * copies)
    return result


def _evidence_for_pages(story: dict[str, Any], pages: list[int]) -> list[dict[str, Any]]:
    allowed = set(pages)
    result: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for item in story.get('sourceEvidence', []):
        if not isinstance(item, dict) or item.get('sourcePage') not in allowed:
            continue
        key = (int(item['sourcePage']), str(item.get('evidence') or ''))
        if key not in seen:
            seen.add(key)
            result.append({'sourcePage': key[0], 'evidence': key[1]})
    return result


def build_episode_shot_plan(story: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    count = resolve_shot_count(story, settings)
    beats = [dict(item) for item in story.get('storyBeats', []) if isinstance(item, dict)]
    source_pages = list(dict.fromkeys(int(page) for page in settings.get('source', {}).get('pages', []) if int(page) > 0))
    if not beats:
        beats = [{'id': 'story', 'summary': story.get('summary') or story.get('title') or 'Story',
                  'sourcePages': source_pages[:1] or [1], 'sourceEvidenceIds': []}]
    groups = _groups(beats, count)
    durations = _allocate_durations(settings.get('duration'), count)
    character_ids = [str(item['id']) for item in story.get('characters', []) if isinstance(item, dict) and item.get('id')]
    occurrence: dict[str, int] = {}
    totals: dict[str, int] = {}
    for group in groups:
        if len(group) == 1:
            beat_id = str(group[0].get('id') or 'beat')
            totals[beat_id] = totals.get(beat_id, 0) + 1
    shots = []
    for index, group in enumerate(groups):
        beat_ids = [str(item.get('id') or f'beat-{index + 1}') for item in group]
        pages = list(dict.fromkeys(page for item in group for page in item.get('sourcePages', []) if page in source_pages))
        if not pages:
            pages = source_pages[:1] or [1]
        purpose = ' / '.join(str(item.get('summary') or item.get('id') or 'Story beat') for item in group)
        if len(group) == 1 and totals.get(beat_ids[0], 1) > 1:
            occurrence[beat_ids[0]] = occurrence.get(beat_ids[0], 0) + 1
            part = occurrence[beat_ids[0]]
            focus = 'establish the setting and characters' if part == 1 else 'advance the visible action without repeating the establishing shot'
            purpose += f" (part {part}/{totals[beat_ids[0]]}: {focus})"
        shots.append({'id': index + 1, 'beatIds': beat_ids, 'purpose': purpose, 'sourcePages': pages,
                      'sourceEvidence': _evidence_for_pages(story, pages), 'characterIds': character_ids,
                      'targetDuration': durations[index]})
    return EpisodeShotPlan.model_validate({'shotCount': count, 'shots': shots}).model_dump()


def episode_cache_key(story: dict[str, Any], model: str, settings: dict[str, Any], count: int) -> str:
    payload = {'story': story, 'model': model, 'revision': EPISODE_PLAN_REVISION,
               'promptVersion': EPISODE_SHOT_PROMPT_VERSION, 'resolvedShotCount': count,
               'settings': {key: settings.get(key) for key in ('level', 'age', 'duration', 'aspectRatio', 'shotCount', 'autoShotCount', 'style', 'language')},
               'source': settings.get('source', {})}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:32]


def compact_shot_context(story: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
    beat_ids = set(slot.get('beatIds', []))
    character_ids = set(slot.get('characterIds', []))
    return {
        'title': story.get('title', ''),
        'storyBeats': [item for item in story.get('storyBeats', [])
                       if isinstance(item, dict) and str(item.get('id')) in beat_ids],
        'characters': [item for item in story.get('characters', [])
                       if isinstance(item, dict) and str(item.get('id')) in character_ids],
        'scenes': [item for item in story.get('scenes', [])
                   if isinstance(item, dict) and set(item.get('sourcePages', [])) & set(slot.get('sourcePages', []))],
        'allowedSpeakerIds': list(slot.get('characterIds', [])),
    }


def normalize_shot_draft(raw: dict[str, Any], slot: dict[str, Any], story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    value = dict(raw or {})
    valid_ids = set(slot.get('characterIds', []))
    names = {str(item.get('name') or '').strip().lower(): str(item.get('id'))
             for item in story.get('characters', []) if isinstance(item, dict) and item.get('id') and item.get('name')}
    speaker = value.get('speaker')
    invalid_speaker = False
    if speaker is not None:
        text = str(speaker).strip()
        if text not in valid_ids:
            mapped = names.get(text.lower())
            if mapped in valid_ids and ',' not in text and ';' not in text and ' and ' not in text.lower():
                text = mapped
            else:
                text = None
                invalid_speaker = True
        value['speaker'] = text
    if not str(value.get('english') or '').strip() and not str(value.get('chinese') or '').strip():
        value['speaker'] = None
    return value, invalid_speaker


def assemble_episode(story: dict[str, Any], settings: dict[str, Any], plan: dict[str, Any],
                     drafts: list[dict[str, Any]]) -> dict[str, Any]:
    source = dict(settings.get('source') or {})
    characters = [dict(item) for item in story.get('characters', []) if isinstance(item, dict)]
    definitions = []
    for item in characters:
        definitions.append({'id': str(item.get('id')), 'name': item.get('name') or 'unknown',
                            'description': item.get('role') or '', 'appearance': item.get('appearance') or '',
                            'clothing': item.get('clothing') or '', 'bodyType': item.get('bodyType') or 'unknown',
                            'accessories': item.get('accessories') or [], 'prompt': item.get('prompt') or '',
                            'negativePrompt': item.get('negativePrompt') or 'identity drift, inconsistent clothing, extra limbs'})
    scenes = [{'id': str(item.get('id') or f'scene_{index + 1:02d}'),
               'description': item.get('description') or item.get('summary') or '',
               'location': item.get('location') or 'unknown'}
              for index, item in enumerate(story.get('scenes', [])) if isinstance(item, dict)]
    shots = []
    for slot, draft in zip(plan['shots'], drafts):
        has_dialogue = bool(str(draft.get('english') or '').strip() or str(draft.get('chinese') or '').strip())
        shots.append({'id': slot['id'], 'title': draft['title'], 'speaker': draft.get('speaker') if has_dialogue else None,
                      'english': draft.get('english', ''), 'chinese': draft.get('chinese', ''),
                      'duration': slot['targetDuration'], 'imagePrompt': draft['imagePrompt'],
                      'videoPrompt': draft['videoPrompt'], 'negativePrompt': draft['negativePrompt'],
                      'sourcePages': slot['sourcePages'], 'sourceEvidence': slot['sourceEvidence'],
                      'dialogueSource': 'adapted' if has_dialogue else 'none'})
    return {'title': story.get('title') or 'Episode', 'level': settings.get('level') or 'Pre-A1',
            'age': settings.get('age') or '3-8', 'duration': sum(item['duration'] for item in shots),
            'aspectRatio': settings.get('aspectRatio') or '9:16',
            'characters': [str(item.get('name') or item.get('id')) for item in characters],
            'characterDefinitions': definitions, 'scenes': scenes, 'shots': shots,
            'source': {'type': 'comic', 'name': source.get('name') or 'unknown',
                       'fileToken': source.get('fileToken') or 'unknown', 'pages': source.get('pages') or [1]}}
