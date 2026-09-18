from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from .models import Episode, SourceEvidence


class CharacterProductionProfile(BaseModel):
    id: str
    name: str = 'unknown'
    appearance: str = ''
    clothing: str = ''
    bodyType: str = 'unknown'
    hairOrFur: str = ''
    accessories: list[str] = Field(default_factory=list)
    prompt: str = ''
    negativePrompt: str = ''


class ProductionStoryContext(BaseModel):
    beatIds: list[str]
    subFocus: str
    sourcePages: list[int]
    sourceEvidence: list[SourceEvidence]
    evidenceIds: list[str]
    dialogueIds: list[str]


class ProductionSettings(BaseModel):
    duration: float = Field(gt=0, le=10)
    aspectRatio: str
    imagePrompt: str
    videoPrompt: str
    negativePrompt: str


class ProductionDialogue(BaseModel):
    speaker: str | None = None
    english: str = ''
    chinese: str = ''
    dialogueSource: str


class ProductionContinuity(BaseModel):
    previousShotId: int | str | None = None
    nextShotId: int | str | None = None
    sceneId: str | None = None
    strength: str
    characterContinuityIds: list[str] = Field(default_factory=list)
    locationContinuity: str = 'transition'
    propContinuity: list[str] = Field(default_factory=list)


class PromptReadiness(BaseModel):
    ready: bool
    checks: list[str] = Field(default_factory=list)


class ProductionShot(BaseModel):
    shotId: int | str
    title: str
    storyContext: ProductionStoryContext
    characterRefs: list[str]
    production: ProductionSettings
    dialogue: ProductionDialogue
    continuity: ProductionContinuity
    taskTypes: list[str] = Field(default_factory=lambda: ['first_frame', 'image_to_video'])
    workflowRequirements: dict[str, Any]
    promptGrounding: str
    imagePromptReadiness: PromptReadiness
    videoPromptReadiness: PromptReadiness
    status: str
    warnings: list[str] = Field(default_factory=list)


class ProductionReadiness(BaseModel):
    readyShots: int
    reviewShots: int
    blockedShots: int
    readyRatio: float
    readyForStoryboard: bool


class ProductionPlan(BaseModel):
    episodeTitle: str
    source: dict[str, Any]
    characters: list[CharacterProductionProfile]
    shots: list[ProductionShot]
    productionReadiness: ProductionReadiness


def _words(value: Any) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9']+", str(value or '').lower()) if len(word) > 3}


def _character_refs(shot: dict[str, Any], profiles: list[dict[str, Any]]) -> list[str]:
    text = ' '.join(str(shot.get(key) or '') for key in ('imagePrompt', 'videoPrompt', 'subFocus', 'english', 'chinese')).lower()
    refs = []
    for profile in profiles:
        cid, name = str(profile['id']), str(profile.get('name') or '')
        if cid.lower() in text or (name and name.lower() != 'unknown' and name.lower() in text):
            refs.append(cid)
    speaker = shot.get('speaker')
    if speaker and speaker not in refs:
        refs.append(str(speaker))
    return refs


def _scene_for_shot(shot: dict[str, Any], scenes: list[dict[str, Any]]) -> dict[str, Any] | None:
    pages = set(shot.get('sourcePages', []))
    for scene in scenes:
        scene_pages = set(scene.get('sourcePages', scene.get('pages', [])))
        if scene_pages & pages:
            return scene
    return None


def _enrich_image(prompt: str, aspect_ratio: str) -> tuple[str, list[str]]:
    additions = []
    lower = prompt.lower()
    if not any(word in lower for word in ('close-up', 'medium shot', 'wide shot', 'camera', 'framing')):
        additions.append('medium shot')
    if 'composition' not in lower:
        additions.append('balanced composition')
    if not any(word in lower for word in ('style', 'comic', 'illustration', 'cinematic')):
        additions.append('source-matched comic illustration style')
    if not any(word in lower for word in ('light', 'lighting', 'moon', 'day', 'night')):
        additions.append('preserve source lighting')
    if aspect_ratio not in prompt:
        additions.append(f'{aspect_ratio} framing')
    return prompt.rstrip(' .') + ('. ' + ', '.join(additions) if additions else ''), additions


def _remove_ungrounded_dialogue(prompt: str) -> tuple[str, bool]:
    parts = re.split(r'(?<=[.!?])\s+', prompt)
    kept = [part for part in parts if not (re.search(r'\b(says?|speaks?|exclaims?|dialogue)\b', part.lower())
                                              or any(mark in part for mark in ('“', '”')))]
    cleaned = ' '.join(kept).strip()
    return (cleaned or 'Hold the source-grounded action without spoken dialogue'), len(kept) != len(parts)


def _enrich_video(prompt: str, duration: float, has_dialogue: bool) -> tuple[str, list[str]]:
    additions = []
    lower = prompt.lower()
    if not any(word in lower for word in ('camera', 'shot', 'pan', 'zoom', 'track')):
        additions.append('fixed camera')
    if not any(word in lower for word in ('motion', 'move', 'turn', 'walk', 'gesture', 'look', 'discuss')):
        additions.append('subtle source-grounded action change')
    if 'environment' not in lower:
        additions.append('subtle environmental motion')
    if 'continu' not in lower and 'identity' not in lower:
        additions.append('preserve character identity and continuity')
    if not any(word in lower for word in ('subtitle', 'on-screen text', 'text artifacts')):
        additions.append('no subtitles or on-screen text')
    if 'second' not in lower:
        additions.append(f'{duration:g}-second duration')
    if has_dialogue and not any(mark in prompt for mark in ("'", '"')):
        additions.append('use only the supplied dialogue')
    return prompt.rstrip(' .') + ('. ' + ', '.join(additions) if additions else ''), additions


def _future_leakage(index: int, shot: dict[str, Any], shots: list[dict[str, Any]]) -> bool:
    current = _words(' '.join([shot.get('subFocus', ''), shot.get('videoPrompt', ''), shot.get('imagePrompt', '')]))
    for future in shots[index + 1:]:
        future_only = _words(future.get('subFocus', '')) - _words(shot.get('subFocus', ''))
        if len(future_only) >= 3 and len(current & future_only) >= max(3, int(len(future_only) * .75)):
            return True
    return False


def build_production_plan(raw_episode: dict[str, Any]) -> dict[str, Any]:
    episode = Episode.model_validate(raw_episode).model_dump()
    profiles = [CharacterProductionProfile.model_validate(item).model_dump() for item in episode['characterDefinitions']]
    valid_characters = {item['id'] for item in profiles}
    valid_pages = set(episode['source']['pages'])
    scenes = list(raw_episode.get('scenes', []))
    shots = list(episode['shots'])
    production_shots = []
    previous_refs: list[str] = []
    previous_scene: dict[str, Any] | None = None
    for index, shot in enumerate(shots):
        warnings: list[str] = []
        blockers: list[str] = []
        refs = _character_refs(shot, profiles)
        invalid_refs = [ref for ref in refs if ref not in valid_characters]
        if invalid_refs or (shot.get('speaker') and shot['speaker'] not in valid_characters): blockers.append('invalid character id')
        if any(page not in valid_pages for page in shot['sourcePages']): blockers.append('invalid source page')
        if any(item['sourcePage'] not in valid_pages for item in shot['sourceEvidence']): blockers.append('invalid source evidence')
        if not shot['sourceEvidence'] or not shot.get('evidenceIds'): warnings.append('evidence trace is incomplete')
        if not shot.get('imagePrompt', '').strip(): blockers.append('missing image prompt')
        if not shot.get('videoPrompt', '').strip(): blockers.append('missing video prompt')
        if not 0 < float(shot.get('duration') or 0) <= 10: blockers.append('invalid duration')
        if _future_leakage(index, shot, shots): blockers.append('future-event leakage')
        has_dialogue = shot.get('dialogueSource') != 'none'
        video_lower = shot.get('videoPrompt', '').lower()
        raw_video_prompt = shot.get('videoPrompt', '')
        if not has_dialogue:
            raw_video_prompt, dialogue_removed = _remove_ungrounded_dialogue(raw_video_prompt)
            if dialogue_removed:
                warnings.append('removed ungrounded spoken dialogue')
        unknown_character_refs = [token for token in re.findall(r'\bcharacter[_-]\w+\b',
                                                                  shot.get('imagePrompt', '') + ' ' + raw_video_prompt,
                                                                  flags=re.IGNORECASE)
                                  if token.lower() not in {cid.lower() for cid in valid_characters}]
        if unknown_character_refs:
            blockers.append('invented character id')

        image_prompt, image_additions = _enrich_image(shot.get('imagePrompt', ''), episode['aspectRatio'])
        video_prompt, video_additions = _enrich_video(raw_video_prompt, shot['duration'], has_dialogue)
        scene = _scene_for_shot(shot, scenes)
        scene_id = str(scene.get('id')) if scene and scene.get('id') else None
        same_scene = bool(index and scene_id and previous_scene and scene_id == str(previous_scene.get('id')))
        same_page = bool(index and set(shots[index - 1]['sourcePages']) & set(shot['sourcePages']))
        same_beat = bool(index and set(shots[index - 1].get('beatIds', [])) & set(shot.get('beatIds', [])))
        continuity_ids = [cid for cid in refs if cid in previous_refs]
        strength = 'strong' if index and same_page and (same_scene or same_beat) else 'transition' if index else 'opening'
        location = str(scene.get('location') or scene.get('description') or 'unknown') if scene else 'unknown'
        if location == 'unknown': warnings.append('location continuity uncertain')
        weak_profiles = [ref for ref in refs if not next((p for p in profiles if p['id'] == ref and (p['appearance'] or p['prompt'])), None)]
        if weak_profiles: warnings.append('character visual definition incomplete: ' + ', '.join(weak_profiles))
        grounding = 'REVIEW' if warnings else 'PASS'
        status = 'BLOCKED' if blockers else 'NEEDS_REVIEW' if warnings else 'READY'
        all_warnings = blockers + warnings
        production_shots.append(ProductionShot.model_validate({
            'shotId': shot['id'], 'title': shot['title'],
            'storyContext': {'beatIds': shot.get('beatIds', []), 'subFocus': shot.get('subFocus', ''),
                             'sourcePages': shot['sourcePages'], 'sourceEvidence': shot['sourceEvidence'],
                             'evidenceIds': shot.get('evidenceIds', []), 'dialogueIds': shot.get('dialogueIds', [])},
            'characterRefs': refs,
            'production': {'duration': shot['duration'], 'aspectRatio': episode['aspectRatio'], 'imagePrompt': image_prompt,
                           'videoPrompt': video_prompt, 'negativePrompt': shot['negativePrompt']},
            'dialogue': {key: shot.get(key) for key in ('speaker', 'english', 'chinese', 'dialogueSource')},
            'continuity': {'previousShotId': shots[index - 1]['id'] if index else None,
                           'nextShotId': shots[index + 1]['id'] if index + 1 < len(shots) else None,
                           'sceneId': scene_id, 'strength': strength, 'characterContinuityIds': continuity_ids,
                           'locationContinuity': 'same' if same_scene else 'transition', 'propContinuity': []},
            'workflowRequirements': {'aspectRatio': episode['aspectRatio'], 'duration': shot['duration'], 'inputImage': None,
                                     'prompt': video_prompt, 'negativePrompt': shot['negativePrompt']},
            'promptGrounding': grounding,
            'imagePromptReadiness': {'ready': bool(image_prompt), 'checks': image_additions},
            'videoPromptReadiness': {'ready': bool(video_prompt), 'checks': video_additions},
            'status': status, 'warnings': all_warnings,
        }).model_dump())
        previous_refs, previous_scene = refs, scene

    ready = sum(item['status'] == 'READY' for item in production_shots)
    review = sum(item['status'] == 'NEEDS_REVIEW' for item in production_shots)
    blocked = sum(item['status'] == 'BLOCKED' for item in production_shots)
    ratio = ready / len(production_shots) if production_shots else 0
    readiness = {'readyShots': ready, 'reviewShots': review, 'blockedShots': blocked, 'readyRatio': round(ratio, 3),
                 'readyForStoryboard': blocked == 0 and (ratio >= .6 or ready + review == len(production_shots))}
    return ProductionPlan.model_validate({'episodeTitle': episode['title'], 'source': episode['source'],
                                           'characters': profiles, 'shots': production_shots,
                                           'productionReadiness': readiness}).model_dump()
