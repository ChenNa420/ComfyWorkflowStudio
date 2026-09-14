from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

InputType = Literal['text','textarea','number','slider','select','boolean','seed','image','video','audio']
InputPurpose = Literal[
    'video-start-frame','video-end-frame','source-image','character-reference',
    'scene-reference','style-reference','pose','depth','lineart','mask',
    'control-image','prompt','negative-prompt','other'
]


class NodeMapping(BaseModel):
    nodeId: str | None = None
    field: str | None = None
    strategy: str | None = None


class WorkflowInput(BaseModel):
    key: str
    label: str
    type: InputType
    required: bool = True
    purpose: InputPurpose | None = None
    description: str = ''
    help: str = ''
    recommended: list[str] = []
    accept: list[str] = []
    mapping: NodeMapping = Field(default_factory=NodeMapping)


class WorkflowParameter(BaseModel):
    key: str
    label: str
    type: InputType
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None
    options: list[Any] = []
    description: str = ''
    mapping: NodeMapping = Field(default_factory=NodeMapping)


class WorkflowOutput(BaseModel):
    key: str
    type: Literal['image','video','audio','text']
    format: str | None = None
    mapping: NodeMapping = Field(default_factory=NodeMapping)


class Dependency(BaseModel):
    name: str
    required: bool = True
    path: str | None = None
    installUrl: str | None = None


class Dependencies(BaseModel):
    models: list[Dependency] = []
    customNodes: list[Dependency] = []


class WorkflowRuntime(BaseModel):
    executionMode: Literal['serial','parallel'] = 'serial'
    durationPolicy: Literal['fixed','dynamic','none'] = 'none'
    allowRetry: bool = True
    retryUnknown: bool = False
    preserveOriginalWorkflow: bool = True
    outputTimeout: int = Field(default=900, ge=1)


class WorkflowGuide(BaseModel):
    summary: str = ''
    steps: list[str] = []
    promptTips: list[str] = []
    warnings: list[str] = []


class WorkflowSource(BaseModel):
    name: str = ''
    url: str = ''


class WorkflowManifest(BaseModel):
    schemaVersion: Literal['1.0'] = '1.0'
    workflowId: str
    name: str
    category: str
    description: str = ''
    difficulty: Literal['easy','medium','advanced'] = 'medium'
    source: WorkflowSource = Field(default_factory=WorkflowSource)
    capabilities: list[str] = []
    recommendedFor: list[str] = []
    notRecommendedFor: list[str] = []
    inputs: list[WorkflowInput] = []
    parameters: list[WorkflowParameter] = []
    outputs: list[WorkflowOutput] = []
    dependencies: Dependencies = Field(default_factory=Dependencies)
    runtime: WorkflowRuntime = Field(default_factory=WorkflowRuntime)
    guide: WorkflowGuide = Field(default_factory=WorkflowGuide)


class WorkflowBindingCreate(BaseModel):
    clientApp: str
    capability: str
    scopeType: Literal['SYSTEM','EPISODE','SHOT']
    scopeId: str | None = None
    workflowId: str
    preset: dict[str, Any] = {}


class GenerationTaskCreate(BaseModel):
    workflowId: str
    clientApp: str | None = None
    projectId: str | None = None
    episodeId: str | None = None
    shotId: str | None = None
    inputs: dict[str, Any] = {}
    parameters: dict[str, Any] = {}
