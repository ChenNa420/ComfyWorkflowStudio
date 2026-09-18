from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.bindings import resolve_binding, upsert_binding
from backend.db import Database
from backend.models import WorkflowBindingCreate


class WorkflowBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / 'studio.sqlite3')
        self.db.initialize()
        now = datetime.now(timezone.utc).isoformat()
        with self.db.connect() as conn:
            for workflow_id, name in [('wf-system', 'System'), ('wf-episode', 'Episode'), ('wf-shot', 'Shot')]:
                manifest = {
                    'schemaVersion': '1.0',
                    'workflowId': workflow_id,
                    'name': name,
                    'category': 'image-to-video',
                    'capabilities': ['image-to-video'],
                    'inputs': [],
                    'parameters': [],
                    'outputs': [{'key': 'video', 'type': 'video'}],
                }
                conn.execute(
                    """
                    INSERT INTO workflows(
                        id,name,category,source,source_url,description,difficulty,
                        original_path,api_workflow_path,cover_path,manifest_json,
                        manifest_version,enabled,compatibility_status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        workflow_id,
                        name,
                        'image-to-video',
                        'test',
                        '',
                        '',
                        'medium',
                        f'{workflow_id}.json',
                        None,
                        None,
                        json.dumps(manifest),
                        1,
                        1,
                        'READY',
                        now,
                        now,
                    ),
                )

    def tearDown(self):
        self.temp.cleanup()

    def bind(self, scope_type: str, workflow_id: str, scope_id: str | None = None):
        return upsert_binding(
            self.db,
            WorkflowBindingCreate(
                clientApp='AiEnglishAnimation',
                capability='image-to-video',
                scopeType=scope_type,
                scopeId=scope_id,
                workflowId=workflow_id,
            ),
        )

    def test_resolution_priority_shot_episode_system(self):
        self.bind('SYSTEM', 'wf-system')
        self.bind('EPISODE', 'wf-episode', 'EP003')
        self.bind('SHOT', 'wf-shot', 'S04')

        shot = resolve_binding(
            self.db,
            client_app='AiEnglishAnimation',
            capability='image-to-video',
            episode_id='EP003',
            shot_id='S04',
        )
        self.assertEqual(shot['source'], 'SHOT')
        self.assertEqual(shot['workflowId'], 'wf-shot')

        episode = resolve_binding(
            self.db,
            client_app='AiEnglishAnimation',
            capability='image-to-video',
            episode_id='EP003',
            shot_id='S05',
        )
        self.assertEqual(episode['source'], 'EPISODE')
        self.assertEqual(episode['workflowId'], 'wf-episode')

        system = resolve_binding(
            self.db,
            client_app='AiEnglishAnimation',
            capability='image-to-video',
            episode_id='EP999',
            shot_id='S01',
        )
        self.assertEqual(system['source'], 'SYSTEM')
        self.assertEqual(system['workflowId'], 'wf-system')

    def test_upsert_replaces_same_scope_without_duplicates(self):
        first = self.bind('EPISODE', 'wf-system', 'EP003')
        second = self.bind('EPISODE', 'wf-episode', 'EP003')
        self.assertEqual(first['id'], second['id'])
        with self.db.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM workflow_bindings WHERE client_app='AiEnglishAnimation' AND capability='image-to-video' AND scope_type='EPISODE' AND scope_id='EP003'"
            ).fetchone()['c']
        self.assertEqual(count, 1)
        self.assertEqual(second['workflowId'], 'wf-episode')


if __name__ == '__main__':
    unittest.main()
