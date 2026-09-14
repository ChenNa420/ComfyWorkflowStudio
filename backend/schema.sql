CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT,
    source_url TEXT,
    description TEXT,
    difficulty TEXT NOT NULL DEFAULT 'medium',
    original_path TEXT NOT NULL,
    api_workflow_path TEXT,
    cover_path TEXT,
    manifest_json TEXT NOT NULL,
    manifest_version INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    compatibility_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflows_category ON workflows(category);
CREATE INDEX IF NOT EXISTS idx_workflows_enabled ON workflows(enabled);

CREATE TABLE IF NOT EXISTS workflow_bindings (
    id TEXT PRIMARY KEY,
    client_app TEXT NOT NULL,
    capability TEXT NOT NULL,
    scope_type TEXT NOT NULL CHECK(scope_type IN ('SYSTEM','EPISODE','SHOT')),
    scope_id TEXT,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    preset_json TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_binding_scope
ON workflow_bindings(client_app, capability, scope_type, COALESCE(scope_id, ''));

CREATE TABLE IF NOT EXISTS generation_tasks (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    client_app TEXT,
    project_id TEXT,
    episode_id TEXT,
    shot_id TEXT,
    status TEXT NOT NULL,
    prompt_id TEXT,
    inputs_json TEXT NOT NULL DEFAULT '{}',
    parameters_json TEXT NOT NULL DEFAULT '{}',
    runtime_workflow_path TEXT,
    progress REAL NOT NULL DEFAULT 0,
    current_node_id TEXT,
    current_node_title TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_generation_tasks_status ON generation_tasks(status);
CREATE INDEX IF NOT EXISTS idx_generation_tasks_episode ON generation_tasks(episode_id, shot_id);

CREATE TABLE IF NOT EXISTS generation_task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES generation_tasks(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    message TEXT,
    data_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_events_task ON generation_task_events(task_id, id);

CREATE TABLE IF NOT EXISTS outputs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES generation_tasks(id) ON DELETE CASCADE,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    thumbnail_path TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT,
    file_path TEXT NOT NULL,
    thumbnail_path TEXT,
    width INTEGER,
    height INTEGER,
    duration REAL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_materials_type ON materials(type);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
