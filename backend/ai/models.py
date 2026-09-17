from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = "1h4b-v3"


class Evidence(BaseModel):
    sourcePage: int = Field(ge=1)
    evidence: str = ""
    evidenceType: str = "visual_fact"
    systemGrounded: bool = False


class Character(BaseModel):
    id: str
    name: str = "unknown"
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    appearance: str = ""
    clothing: str = ""
    bodyType: str = "unknown"
    hairOrFur: str = "unknown"
    accessories: list[str] = Field(default_factory=list)
    prompt: str = ""
    negativePrompt: str = "identity drift, inconsistent clothing, extra limbs"
    personality: str = "unknown"
    role: str = "unknown"
    firstSeenPage: int = Field(ge=1)
    pages: list[int] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    needsReview: bool = False


class Scene(BaseModel):
    id: str
    location: str = "unknown"
    timeOfDay: str = "unknown"
    description: str = ""
    pages: list[int] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    mood: str = "unknown"
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)


class Dialogue(BaseModel):
    page: int = Field(ge=1)
    speakerId: str | None = None
    text: str
    language: str = "unknown"
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: str = ""
    evidenceType: str = "speech_bubble"
    systemGrounded: bool = False
    speakerResolution: Literal['resolved', 'unknown', 'conflict'] = 'unknown'
    speakerDescription: str = ""
    bubblePosition: str = "unknown"
    needsReview: bool = False


class PlotEvent(BaseModel):
    id: str
    pages: list[int] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    action: str
    cause: str = "unknown"
    result: str = "unknown"
    importance: str = "supporting"
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)


class VisualStyle(BaseModel):
    medium: str = "unknown"
    lineStyle: str = "unknown"
    colorPalette: str = "unknown"
    lighting: str = "unknown"
    composition: str = "unknown"
    notes: str = ""


class Prop(BaseModel):
    id: str
    name: str = "unknown"
    description: str = ""
    pages: list[int] = Field(default_factory=list)
    ownerCharacterId: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)


class Location(BaseModel):
    id: str
    name: str = "unknown"
    description: str = ""
    pages: list[int] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)


class StorySummary(BaseModel):
    titleGuess: str = "unknown"
    premise: str = ""
    beginning: str = ""
    middle: str = ""
    ending: str = ""
    conflict: str = "unknown"
    resolution: str = "unknown"
    themes: list[str] = Field(default_factory=list)
    tone: str = "unknown"


class SemanticAnalysis(BaseModel):
    id: str = ""
    characters: list[Character] = Field(default_factory=list, max_length=48)
    scenes: list[Scene] = Field(default_factory=list, max_length=24)
    dialogues: list[Dialogue] = Field(default_factory=list, max_length=128)
    plotEvents: list[PlotEvent] = Field(default_factory=list, max_length=48)
    visualStyle: VisualStyle = Field(default_factory=VisualStyle)
    props: list[Prop] = Field(default_factory=list, max_length=32)
    locations: list[Location] = Field(default_factory=list, max_length=16)
    storySummary: StorySummary = Field(default_factory=StorySummary)
    warnings: list[str] = Field(default_factory=list, max_length=8)
    needsReview: bool = False

    @model_validator(mode='after')
    def require_content(self):
        meaningful = bool(self.characters or self.scenes or self.dialogues or self.plotEvents or self.storySummary.premise.strip())
        if not meaningful:
            raise ValueError('EMPTY_SEMANTIC_ANALYSIS')
        return self

    @classmethod
    def validate_provider(cls, value: dict[str, Any]) -> "SemanticAnalysis":
        return cls.model_validate(value)


class PageCharacter(BaseModel):
    temporaryId: str
    name: str | None = None
    appearance: str = ""
    clothing: str = ""
    bodyType: str = "unknown"
    hairOrFur: str = "unknown"
    accessories: list[str] = Field(default_factory=list)
    position: str = "unknown"
    roleHint: str = "unknown"
    confidence: float = Field(default=0, ge=0, le=1)
    needsReview: bool = False


class PageDialogue(BaseModel):
    text: str
    speakerTemporaryId: str | int | None = None
    speakerDescription: str = ""
    bubblePosition: str = "unknown"
    confidence: float = Field(default=0, ge=0, le=1)
    needsReview: bool = False

    @field_validator('confidence', mode='before')
    @classmethod
    def normalize_confidence(cls, value: Any) -> float:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            return 0
        if number > 1:
            number /= 100
        return max(0, min(1, number))


class PageDialogueResult(BaseModel):
    page: int = Field(ge=1)
    dialogues: list[PageDialogue] = Field(default_factory=list, max_length=64)
    warnings: list[str] = Field(default_factory=list, max_length=8)


class PageScene(BaseModel):
    location: str = "unknown"
    timeOfDay: str = "unknown"
    description: str = ""
    mood: str = "unknown"
    confidence: float = Field(default=0, ge=0, le=1)
    needsReview: bool = False


class PagePlotEvent(BaseModel):
    action: str
    characterTemporaryIds: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    needsReview: bool = False


class PageProp(BaseModel):
    name: str
    description: str = ""
    ownerTemporaryId: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)


class PageVisualResult(BaseModel):
    page: int = Field(ge=1)
    characters: list[PageCharacter] = Field(default_factory=list, max_length=12)
    scene: PageScene | None = None
    plotEvents: list[PagePlotEvent] = Field(default_factory=list, max_length=12)
    props: list[PageProp] = Field(default_factory=list, max_length=12)
    visualNotes: str = ""
    warnings: list[str] = Field(default_factory=list, max_length=8)


class SourceEvidence(BaseModel):
    id: str | None = None
    sourcePage: int = Field(ge=1)
    evidence: str = ''


class AdaptationEvidenceRef(BaseModel):
    id: str
    sourcePage: int = Field(ge=1)
    kind: str
    sourceId: str


class AdaptationDialogue(BaseModel):
    id: str
    sourcePage: int = Field(ge=1)
    sceneId: str | None = None
    speaker: str = 'unknown'
    text: str
    dialogueSource: Literal['source'] = 'source'
    sourceEvidenceIds: list[str] = Field(default_factory=list)


class AdaptationDialogueSummary(BaseModel):
    sourcePage: int = Field(ge=1)
    sceneId: str | None = None
    omittedCount: int = Field(ge=0)
    summary: str


class AdaptationCharacter(BaseModel):
    id: str
    name: str = 'unknown'
    role: str = 'unknown'
    classification: Literal['main', 'supporting', 'background']
    pages: list[int] = Field(default_factory=list)
    summary: str = ''
    confidence: float = Field(default=0, ge=0, le=1)
    needsReview: bool = False
    sourceEvidenceIds: list[str] = Field(default_factory=list)


class AdaptationContext(BaseModel):
    sourcePages: list[int] = Field(min_length=1)
    tone: str = 'unknown'
    premise: str = ''
    characters: list[AdaptationCharacter] = Field(default_factory=list)
    backgroundCharacters: list[AdaptationCharacter] = Field(default_factory=list)
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    storyBeats: list[dict[str, Any]] = Field(default_factory=list)
    keyDialogues: list[AdaptationDialogue] = Field(default_factory=list)
    dialogueSummary: list[AdaptationDialogueSummary] = Field(default_factory=list)
    plotEvents: list[dict[str, Any]] = Field(default_factory=list)
    sourceEvidence: list[AdaptationEvidenceRef] = Field(default_factory=list)


class AdaptationBeat(BaseModel):
    id: str
    summary: str
    sourcePages: list[int] = Field(min_length=1)
    sourceEvidenceIds: list[str] = Field(default_factory=list)


class AdaptationPlan(BaseModel):
    title: str
    premise: str
    mainCharacters: list[str] = Field(default_factory=list)
    beginning: str
    middle: str
    ending: str
    conflict: str = 'unknown'
    resolution: str = 'unknown'
    narrativeType: str = 'narrative_story'
    recommendedShotCount: int | None = Field(default=None, ge=1, le=12)
    beats: list[AdaptationBeat] = Field(min_length=1, max_length=16)
    sourceEvidenceIds: list[str] = Field(default_factory=list)
    unassignedDialogue: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AdaptedStoryDraft(BaseModel):
    title: str
    logline: str
    summary: str
    characters: list[dict[str, Any]]
    scenes: list[dict[str, Any]]
    storyBeats: list[AdaptationBeat] = Field(min_length=1, max_length=16)
    ending: str
    learningGoals: list[str]
    sourceEvidenceIds: list[str] = Field(default_factory=list)
    adaptationNotes: list[str] = Field(default_factory=list)


class AdaptedStory(BaseModel):
    title: str
    logline: str
    summary: str
    characters: list[dict[str, Any]]
    scenes: list[dict[str, Any]]
    storyBeats: list[dict[str, Any] | str]
    ending: str
    learningGoals: list[str]
    sourceEvidence: list[SourceEvidence]
    keyDialogues: list[AdaptationDialogue] = Field(default_factory=list)
    adaptationNotes: list[str] = Field(default_factory=list)
    narrativeType: str = 'narrative_story'
    recommendedShotCount: int | None = Field(default=None, ge=1, le=12)


class EpisodeCharacter(BaseModel):
    id: str
    name: str = 'unknown'
    description: str = ''
    appearance: str = ''
    clothing: str = ''
    bodyType: str = 'unknown'
    accessories: list[str] = Field(default_factory=list)
    prompt: str = ''
    negativePrompt: str = 'identity drift, inconsistent clothing, extra limbs'


class EpisodeScene(BaseModel):
    id: str
    description: str = ''
    location: str = 'unknown'


class EpisodeShotSlot(BaseModel):
    id: int = Field(ge=1)
    beatIds: list[str] = Field(min_length=1)
    purpose: str
    subFocus: str
    sourcePages: list[int] = Field(min_length=1)
    sourceEvidence: list[SourceEvidence]
    evidenceIds: list[str] = Field(default_factory=list)
    dialogueIds: list[str] = Field(default_factory=list)
    assignedDialogues: list[AdaptationDialogue] = Field(default_factory=list)
    evidenceMappingMode: Literal['exact_beat', 'page_fallback', 'none'] = 'none'
    sequenceIndex: int = Field(default=1, ge=1)
    sequenceTotal: int = Field(default=1, ge=1)
    characterIds: list[str] = Field(default_factory=list)
    targetDuration: float = Field(gt=0, le=10)


class EpisodeShotPlan(BaseModel):
    shotCount: int = Field(ge=1, le=12)
    shots: list[EpisodeShotSlot] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def exact_contiguous_shots(self):
        if len(self.shots) != self.shotCount:
            raise ValueError('shot plan count mismatch')
        if [item.id for item in self.shots] != list(range(1, self.shotCount + 1)):
            raise ValueError('shot plan ids must be continuous')
        return self


class EpisodeShotDraft(BaseModel):
    title: str
    speaker: str | None = None
    english: str = ''
    chinese: str = ''
    imagePrompt: str
    videoPrompt: str
    negativePrompt: str
    durationSuggestion: float | None = None


class EpisodeShot(BaseModel):
    id: int | str
    title: str
    speaker: str | None = None
    english: str = ''
    chinese: str = ''
    duration: float = Field(gt=0, le=10)
    imagePrompt: str
    videoPrompt: str
    negativePrompt: str
    sourcePages: list[int] = Field(min_length=1)
    sourceEvidence: list[SourceEvidence]
    beatIds: list[str] = Field(default_factory=list)
    subFocus: str = ''
    evidenceIds: list[str] = Field(default_factory=list)
    dialogueIds: list[str] = Field(default_factory=list)
    evidenceMappingMode: Literal['exact_beat', 'page_fallback', 'none'] = 'none'
    sequenceIndex: int = Field(default=1, ge=1)
    sequenceTotal: int = Field(default=1, ge=1)
    redundantShot: bool = False
    dialogueSource: Literal['source', 'adapted', 'none']

    @model_validator(mode='after')
    def pages_positive(self):
        if any(page < 1 for page in self.sourcePages): raise ValueError('invalid source page')
        return self


class EpisodeSource(BaseModel):
    type: Literal['comic']
    name: str
    fileToken: str
    pages: list[int] = Field(min_length=1)


class Episode(BaseModel):
    title: str
    level: str
    age: str
    duration: float = Field(gt=0)
    aspectRatio: str
    characters: list[str]
    characterDefinitions: list[EpisodeCharacter]
    scenes: list[EpisodeScene]
    shots: list[EpisodeShot] = Field(min_length=1)
    source: EpisodeSource

    @model_validator(mode='after')
    def speakers_exist(self):
        keys = {item.id for item in self.characterDefinitions}
        if any(shot.speaker is not None and shot.speaker not in keys for shot in self.shots):
            raise ValueError('speaker must reference characterDefinitions')
        allowed = set(self.source.pages)
        if any(page not in allowed for shot in self.shots for page in shot.sourcePages):
            raise ValueError('shot sourcePages must reference Episode source pages')
        if any(item.sourcePage not in allowed for shot in self.shots for item in shot.sourceEvidence):
            raise ValueError('shot sourceEvidence must reference Episode source pages')
        return self
