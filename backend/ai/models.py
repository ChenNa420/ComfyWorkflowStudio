from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

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

    @classmethod
    def validate_provider(cls, value: dict[str, Any]) -> "SemanticAnalysis":
        return cls.model_validate(value)

