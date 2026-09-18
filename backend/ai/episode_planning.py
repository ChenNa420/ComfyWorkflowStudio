from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .models import EpisodeShotPlan

EPISODE_PLAN_REVISION = '1h4d-plan-v1'
EPISODE_SHOT_PROMPT_VERSION = '1h4d-shot-p2'


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


def _clean(value: Any, limit: int = 180) -> str:
    text = ' '.join(str(value or '').split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def _catalog(story: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    ordered = []
    by_id = {}
    for item in story.get('sourceEvidence', []):
        if not isinstance(item, dict) or not isinstance(item.get('sourcePage'), int):
            continue
        value = {'id': item.get('id'), 'sourcePage': item['sourcePage'], 'evidence': _clean(item.get('evidence'))}
        ordered.append(value)
        if value['id']:
            by_id[str(value['id'])] = value
    return by_id, ordered


def _distribute(values: list[dict[str, Any]], count: int) -> list[list[dict[str, Any]]]:
    return [values[index * len(values) // count:(index + 1) * len(values) // count] for index in range(count)]


def _scene_text(story: dict[str, Any], pages: list[int]) -> str:
    allowed = set(pages)
    for scene in story.get('scenes', []):
        if not isinstance(scene, dict) or not (set(scene.get('sourcePages', scene.get('pages', []))) & allowed):
            continue
        return _clean(scene.get('description') or scene.get('summary') or scene.get('location'))
    return ''


def _focus(summary: str, scene: str, evidence: list[dict[str, Any]], dialogues: list[dict[str, Any]],
           index: int, total: int, narrative_type: str) -> str:
    detail = ''
    if dialogues:
        detail = f"Use the next grounded dialogue: {_clean(dialogues[0].get('text'), 90)}"
    elif evidence:
        detail = f"Show the grounded detail: {_clean(evidence[0].get('evidence'), 100)}"
    if total == 1:
        prefix = 'Present this process step' if narrative_type == 'educational_process' else 'Show this story beat'
        return _clean(f'{prefix}: {summary}. {detail}', 260)
    if index == 1:
        prefix = 'Establish the setting and participants for'
        anchor = scene or summary
        return _clean(f'{prefix} {anchor}. {detail}', 260)
    prefix = f'Progress part {index} of {total} using the next grounded action or dialogue from'
    return _clean(f'{prefix} {summary}. {detail}', 260)


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
    evidence_by_id, ordered_evidence = _catalog(story)
    dialogues = [dict(item) for item in story.get('keyDialogues', []) if isinstance(item, dict)]
    narrative_type = str(story.get('narrativeType') or 'narrative_story')

    totals: dict[tuple[str, ...], int] = {}
    for group in groups:
        key = tuple(str(item.get('id') or 'beat') for item in group)
        totals[key] = totals.get(key, 0) + 1
    occurrences: dict[tuple[str, ...], int] = {}
    resource_sets: dict[tuple[str, ...], tuple[list[list[dict[str, Any]]], list[list[dict[str, Any]]], str]] = {}
    used_dialogue_ids: set[str] = set()
    for group in groups:
        key = tuple(str(item.get('id') or 'beat') for item in group)
        if key in resource_sets:
            continue
        pages = list(dict.fromkeys(page for item in group for page in item.get('sourcePages', []) if page in source_pages))
        exact_ids = list(dict.fromkeys(str(eid) for item in group for eid in item.get('sourceEvidenceIds', [])))
        exact = [evidence_by_id[eid] for eid in exact_ids if eid in evidence_by_id]
        if exact:
            evidence, mode = exact, 'exact_beat'
        else:
            evidence = [item for item in ordered_evidence if item['sourcePage'] in set(pages)]
            mode = 'page_fallback' if evidence else 'none'
        eligible_dialogues = [item for item in dialogues if item.get('sourcePage') in set(pages)
                              and str(item.get('id')) not in used_dialogue_ids
                              and (not exact_ids or set(item.get('sourceEvidenceIds', [])) & set(exact_ids))]
        used_dialogue_ids.update(str(item.get('id')) for item in eligible_dialogues)
        resource_sets[key] = (_distribute(evidence, totals[key]), _distribute(eligible_dialogues, totals[key]), mode)

    shots = []
    for position, group in enumerate(groups):
        beat_ids = [str(item.get('id') or f'beat-{position + 1}') for item in group]
        key = tuple(beat_ids)
        occurrences[key] = occurrences.get(key, 0) + 1
        sequence_index, sequence_total = occurrences[key], totals[key]
        pages = list(dict.fromkeys(page for item in group for page in item.get('sourcePages', []) if page in source_pages))
        if not pages:
            pages = source_pages[:1] or [1]
        evidence_parts, dialogue_parts, mode = resource_sets[key]
        evidence = evidence_parts[sequence_index - 1]
        assigned_dialogues = dialogue_parts[sequence_index - 1]
        summary = ' / '.join(_clean(item.get('summary') or item.get('id') or 'Story beat') for item in group)
        sub_focus = _focus(summary, _scene_text(story, pages), evidence, assigned_dialogues,
                           sequence_index, sequence_total, narrative_type)
        shots.append({
            'id': position + 1, 'beatIds': beat_ids, 'purpose': sub_focus, 'subFocus': sub_focus,
            'sourcePages': pages, 'sourceEvidence': evidence,
            'evidenceIds': [str(item['id']) for item in evidence if item.get('id')],
            'dialogueIds': [str(item['id']) for item in assigned_dialogues if item.get('id')],
            'assignedDialogues': assigned_dialogues, 'evidenceMappingMode': mode,
            'sequenceIndex': sequence_index, 'sequenceTotal': sequence_total,
            'characterIds': character_ids, 'targetDuration': durations[position],
        })
    plan = EpisodeShotPlan.model_validate({'shotCount': count, 'shots': shots}).model_dump()
    validate_plan_quality(story, plan)
    return plan


def _normalized(value: str) -> set[str]:
    return {token for token in re.findall(r'[a-z0-9]+', value.lower()) if token not in {'the', 'a', 'an', 'and', 'of', 'to'}}


def duplicate_flags(plan: dict[str, Any]) -> list[bool]:
    flags = [False] * len(plan.get('shots', []))
    for index in range(1, len(flags)):
        previous, current = plan['shots'][index - 1], plan['shots'][index]
        left, right = _normalized(previous.get('purpose', '')), _normalized(current.get('purpose', ''))
        similarity = len(left & right) / max(1, len(left | right))
        same_sources = (previous.get('evidenceIds', []) == current.get('evidenceIds', []) and
                        previous.get('dialogueIds', []) == current.get('dialogueIds', []))
        flags[index] = similarity >= .8 and same_sources
    return flags


def plan_quality(story: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    expected = [str(item.get('id')) for item in story.get('storyBeats', []) if isinstance(item, dict)]
    covered = list(dict.fromkeys(str(bid) for shot in plan.get('shots', []) for bid in shot.get('beatIds', [])))
    missing = [beat_id for beat_id in expected if beat_id not in covered]
    pages = [page for shot in plan.get('shots', []) for page in shot.get('sourcePages', [])]
    positions = [expected.index(beat_id) for shot in plan.get('shots', []) for beat_id in shot.get('beatIds', []) if beat_id in expected]
    flags = duplicate_flags(plan)
    return {
        'beatCoverage': {'covered': len(expected) - len(missing), 'total': len(expected), 'missingBeatIds': missing},
        'storyOrderPreserved': positions == sorted(positions),
        'sourcePageOrderPreserved': pages == sorted(pages),
        'duplicateWarnings': [plan['shots'][index]['id'] for index, flag in enumerate(flags) if flag],
        'evidenceMappingMode': [shot.get('evidenceMappingMode', 'none') for shot in plan.get('shots', [])],
    }


def validate_plan_quality(story: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    quality = plan_quality(story, plan)
    if quality['beatCoverage']['missingBeatIds']:
        raise ValueError('EPISODE_MISSING_STORY_BEAT')
    if not quality['storyOrderPreserved']:
        raise ValueError('EPISODE_STORY_ORDER_INVALID')
    if not quality['sourcePageOrderPreserved']:
        raise ValueError('EPISODE_SOURCE_PAGE_ORDER_INVALID')
    return quality


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
        'title': story.get('title', ''), 'narrativeType': story.get('narrativeType', 'narrative_story'),
        'storyBeats': [item for item in story.get('storyBeats', []) if isinstance(item, dict) and str(item.get('id')) in beat_ids],
        'characters': [item for item in story.get('characters', []) if isinstance(item, dict) and str(item.get('id')) in character_ids],
        'scenes': [item for item in story.get('scenes', []) if isinstance(item, dict) and set(item.get('sourcePages', item.get('pages', []))) & set(slot.get('sourcePages', []))],
        'assignedDialogues': slot.get('assignedDialogues', []), 'allowedSpeakerIds': list(slot.get('characterIds', [])),
    }


def normalize_shot_draft(raw: dict[str, Any], slot: dict[str, Any], story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    value = dict(raw or {})
    valid_ids = set(slot.get('characterIds', []))
    names = {str(item.get('name') or '').strip().lower(): str(item.get('id')) for item in story.get('characters', []) if isinstance(item, dict) and item.get('id') and item.get('name')}
    speaker = value.get('speaker')
    invalid_speaker = False
    if speaker is not None:
        text = str(speaker).strip()
        if text not in valid_ids:
            mapped = names.get(text.lower())
            if mapped in valid_ids and ',' not in text and ';' not in text and ' and ' not in text.lower():
                text = mapped
            else:
                text = None; invalid_speaker = True
        value['speaker'] = text
    if not str(value.get('english') or '').strip() and not str(value.get('chinese') or '').strip():
        value['speaker'] = None
    return value, invalid_speaker


def assemble_episode(story: dict[str, Any], settings: dict[str, Any], plan: dict[str, Any], drafts: list[dict[str, Any]]) -> dict[str, Any]:
    source = dict(settings.get('source') or {})
    characters = [dict(item) for item in story.get('characters', []) if isinstance(item, dict)]
    definitions = [{'id': str(item.get('id')), 'name': item.get('name') or 'unknown', 'description': item.get('role') or '',
                    'appearance': item.get('appearance') or '', 'clothing': item.get('clothing') or '',
                    'bodyType': item.get('bodyType') or 'unknown', 'hairOrFur': item.get('hairOrFur') or '',
                    'accessories': item.get('accessories') or [],
                    'prompt': item.get('prompt') or '', 'negativePrompt': item.get('negativePrompt') or 'identity drift, inconsistent clothing, extra limbs'} for item in characters]
    scenes = [{'id': str(item.get('id') or f'scene_{index + 1:02d}'), 'description': item.get('description') or item.get('summary') or '',
               'location': item.get('location') or 'unknown'} for index, item in enumerate(story.get('scenes', [])) if isinstance(item, dict)]
    flags = duplicate_flags(plan)
    shots = []
    for index, (slot, draft) in enumerate(zip(plan['shots'], drafts)):
        has_dialogue = bool(str(draft.get('english') or '').strip() or str(draft.get('chinese') or '').strip())
        shots.append({'id': slot['id'], 'title': draft['title'], 'speaker': draft.get('speaker') if has_dialogue else None,
                      'english': draft.get('english', ''), 'chinese': draft.get('chinese', ''), 'duration': slot['targetDuration'],
                      'imagePrompt': draft['imagePrompt'], 'videoPrompt': draft['videoPrompt'], 'negativePrompt': draft['negativePrompt'],
                      'sourcePages': slot['sourcePages'], 'sourceEvidence': slot['sourceEvidence'], 'beatIds': slot['beatIds'],
                      'subFocus': slot['subFocus'], 'evidenceIds': slot['evidenceIds'], 'dialogueIds': slot['dialogueIds'],
                      'evidenceMappingMode': slot['evidenceMappingMode'], 'sequenceIndex': slot['sequenceIndex'],
                      'sequenceTotal': slot['sequenceTotal'], 'redundantShot': flags[index],
                      'dialogueSource': 'adapted' if has_dialogue else 'none'})
    return {'title': story.get('title') or 'Episode', 'level': settings.get('level') or 'Pre-A1', 'age': settings.get('age') or '3-8',
            'duration': sum(item['duration'] for item in shots), 'aspectRatio': settings.get('aspectRatio') or '9:16',
            'characters': [str(item.get('name') or item.get('id')) for item in characters], 'characterDefinitions': definitions,
            'scenes': scenes, 'shots': shots, 'source': {'type': 'comic', 'name': source.get('name') or 'unknown',
            'fileToken': source.get('fileToken') or 'unknown', 'pages': source.get('pages') or [1]}}
