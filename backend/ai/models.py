from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1h3-v1"


class Evidence(BaseModel):
    sourcePage: int = Field(ge=1)
    evidence: str = ""


class Character(BaseModel):
    id: str
    name: str = "unknown"
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    appearance: str = ""
    clothing: str = ""
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
    characters: list[Character] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    dialogues: list[Dialogue] = Field(default_factory=list)
    plotEvents: list[PlotEvent] = Field(default_factory=list)
    visualStyle: VisualStyle = Field(default_factory=VisualStyle)
    props: list[Prop] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    storySummary: StorySummary = Field(default_factory=StorySummary)
    warnings: list[str] = Field(default_factory=list)
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


class SourceEvidence(BaseModel):
    sourcePage: int = Field(ge=1)
    evidence: str = ''


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


class EpisodeCharacter(BaseModel):
    id: str
    name: str = 'unknown'
    description: str = ''


class EpisodeScene(BaseModel):
    id: str
    description: str = ''
    location: str = 'unknown'


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
        return self
