from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.db import Database
from backend.models import WorkflowManifest
from backend.workflow.dependencies import classify_model_type, extract_comfy_model_catalog
from backend.workflow.knowledge import build_workflow_card
from backend.workflow.manifest import load_manifest, save_manifest
from backend.workflow.manifest_history import (
    list_manifest_versions,
    rollback_manifest_version,
    record_manifest_version,
    save_manifest_with_history,
)
from backend.workflow.manifest_review import manifest_review_batch


class Phase1F3GovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.package = self.root / 'wf-test'
        self.package.mkdir()
        self.manifest_path = self.package / 'manifest.json'
        self.original_path = self.package / 'original.json'
        self.original_path.write_text('{"immutable":true}\n', encoding='utf-8')
        self.analysis = {
            'format': 'ui-workflow',
            'nodeCount': 3,
            'nodeTypes': ['CheckpointLoaderSimple', 'KSampler', 'SaveImage'],
            'inputs': [],
        }
        (self.package / 'analysis.json').write_text(json.dumps(self.analysis), encoding='utf-8')
        self.manifest = WorkflowManifest.model_validate({
            'schemaVersion': '1.0',
            'workflowId': 'wf-test',
            'name': 'Test Workflow',
            'category': 'text-to-image',
            'description': '这是一个用于 Phase 1F-3 版本历史测试的工作流说明。',
            'difficulty': 'medium',
            'source': {'name': 'test', 'url': ''},
            'capabilities': ['text-to-image'],
            'recommendedFor': ['测试'],
            'notRecommendedFor': ['生产'],
            'inputs': [],
            'parameters': [],
            'outputs': [{'key': 'image', 'type': 'image', 'format': 'png', 'mapping': {'nodeId': '3'}}],
            'dependencies': {'models': [{'name': 'base.safetensors', 'required': True}], 'customNodes': []},
            'runtime': {
                'executionMode': 'serial',
                'durationPolicy': 'none',
                'allowRetry': True,
                'retryUnknown': False,
                'preserveOriginalWorkflow': True,
                'outputTimeout': 900,
            },
            'guide': {'summary': '测试流程', 'steps': ['提交任务'], 'promptTips': [], 'warnings': []},
        })
        save_manifest(self.manifest, self.manifest_path)
        self.db = Database(self.root / 'studio.sqlite3')
        self.db.initialize()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflows(
                    id,name,category,source,source_url,description,difficulty,original_path,
                    api_workflow_path,cover_path,manifest_json,manifest_version,enabled,
                    compatibility_status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
                """,
                (
                    self.manifest.workflowId, self.manifest.name, self.manifest.category,
                    'test', '', self.manifest.description, self.manifest.difficulty,
                    str(self.original_path), None, None,
                    json.dumps(self.manifest.model_dump(mode='json'), ensure_ascii=False),
                    1, 1, 'READY_FOR_DEPENDENCY_CHECK',
                ),
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_manifest_history_ids_remain_unique_when_clock_stamp_collides(self):
        with patch('backend.workflow.manifest_history._stamp', return_value='20260916T120000000000Z'):
            first = record_manifest_version(self.manifest_path, self.manifest, action='baseline')
            second = record_manifest_version(self.manifest_path, self.manifest, action='same-stamp')
        self.assertNotEqual(first['versionId'], second['versionId'])
        self.assertEqual(len(list_manifest_versions(self.manifest_path)), 2)

    def test_model_catalog_classifies_checkpoint_vae_controlnet_and_lora(self):
        object_info = {
            'CheckpointLoaderSimple': {'input': {'required': {'ckpt_name': [['base.safetensors'], {}]}}},
            'VAELoader': {'input': {'required': {'vae_name': [['sdxl_vae.safetensors'], {}]}}},
            'ControlNetLoader': {'input': {'required': {'control_net_name': [['depth-control.safetensors'], {}]}}},
            'LoraLoader': {'input': {'required': {'lora_name': [['style.safetensors'], {}]}}},
        }
        catalog = extract_comfy_model_catalog(object_info)
        by_name = {item['name']: item['modelType'] for item in catalog}
        self.assertEqual(by_name['base.safetensors'], 'checkpoint')
        self.assertEqual(by_name['sdxl_vae.safetensors'], 'vae')
        self.assertEqual(by_name['depth-control.safetensors'], 'controlnet')
        self.assertEqual(by_name['style.safetensors'], 'lora')

    def test_explicit_model_field_wins_over_node_name(self):
        self.assertEqual(
            classify_model_type('LTXVAudioVAELoader', 'ckpt_name', 'ltx-model.safetensors'),
            'checkpoint',
        )
        self.assertEqual(
            classify_model_type('CreateHookModelAsLora', 'ckpt_name', 'model.safetensors'),
            'checkpoint',
        )
        self.assertEqual(classify_model_type('UNETLoader', 'unet_name', 'wan.gguf'), 'diffusion-model')

    def test_live_missing_dependency_overrides_manifest_ready_health(self):
        card = build_workflow_card(
            self.manifest_path,
            self.manifest,
            db_row={'compatibility_status': 'READY_FOR_DEPENDENCY_CHECK'},
            dependency_status='MISSING_DEPENDENCIES',
        )
        self.assertEqual(card['health'], 'MISSING_DEPENDENCIES')
        self.assertEqual(card['dependencyStatus'], 'MISSING_DEPENDENCIES')

    def test_manifest_history_can_rollback_without_touching_original(self):
        original_hash = hashlib.sha256(self.original_path.read_bytes()).hexdigest()
        payload = self.manifest.model_dump(mode='json')
        payload['description'] = '更新后的 Manifest 描述，用于测试版本历史和回滚。'
        updated = WorkflowManifest.model_validate(payload)
        save_manifest_with_history(
            self.db,
            self.manifest_path,
            self.manifest,
            updated,
            action='unit-test-update',
        )
        versions = list_manifest_versions(self.manifest_path)
        baseline = next(item for item in versions if item['action'] == 'baseline')
        self.assertGreaterEqual(len(versions), 3)
        self.assertEqual(load_manifest(self.manifest_path).description, updated.description)

        with patch('backend.workflow.manifest_history.discover_manifests', return_value=[(self.manifest_path, updated)]):
            result = rollback_manifest_version(self.db, self.manifest.workflowId, baseline['versionId'])
        self.assertIsNotNone(result)
        self.assertNotIn('error', result)
        self.assertEqual(load_manifest(self.manifest_path).description, self.manifest.description)
        self.assertEqual(hashlib.sha256(self.original_path.read_bytes()).hexdigest(), original_hash)
        with self.db.connect() as conn:
            row = conn.execute('SELECT manifest_json FROM workflows WHERE id=?', (self.manifest.workflowId,)).fetchone()
        self.assertEqual(json.loads(row['manifest_json'])['description'], self.manifest.description)

    def test_batch_review_is_read_only_preview(self):
        with patch('backend.workflow.manifest_review.discover_manifests', return_value=[(self.manifest_path, self.manifest)]):
            result = manifest_review_batch([self.manifest.workflowId, 'missing-id'])
        self.assertFalse(result['writeMode'])
        self.assertEqual(result['requested'], 2)
        self.assertEqual(result['found'], 1)
        self.assertEqual(result['missingWorkflowIds'], ['missing-id'])


if __name__ == '__main__':
    unittest.main()
