from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.comfy.client import ComfyClientError
from backend.db import Database
from backend.models import WorkflowManifest
from backend.workflow.dependencies import dependency_inventory, extract_comfy_model_options, match_declared_model
from backend.workflow.manifest import load_manifest, save_manifest
from backend.workflow.manifest_review import apply_safe_manifest_review, manifest_review_item


class FakeComfyClient:
    base_url = 'http://127.0.0.1:8188'

    def object_info(self):
        return {
            'CheckpointLoaderSimple': {
                'input': {'required': {'ckpt_name': [['models/base/MiniMaxH3.safetensors'], {}]}}
            },
            'MiniMaxH3ImageToVideo': {'input': {'required': {}}},
            'KSampler': {'input': {'required': {}}},
            'SaveVideo': {'input': {'required': {}}},
        }


class OfflineComfyClient:
    base_url = 'http://127.0.0.1:8188'

    def object_info(self):
        raise ComfyClientError('offline')


class Phase1F2DependencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.package = self.root / 'wf-minimax'
        self.package.mkdir()
        self.manifest_path = self.package / 'manifest.json'
        self.original_path = self.package / 'original.json'
        self.original_path.write_text('{"immutable":true}\n', encoding='utf-8')
        self.analysis = {
            'format': 'ui-workflow',
            'nodeCount': 4,
            'nodeTypes': ['MiniMaxH3ImageToVideo', 'KSampler', 'SaveVideo'],
            'inputs': [
                {
                    'key': 'first-frame',
                    'purpose': 'video-start-frame',
                    'description': 'First frame',
                    'help': 'Start image',
                    'mapping': {'nodeId': '10', 'field': 'image'},
                    'analysisConfidence': 0.95,
                }
            ],
        }
        (self.package / 'analysis.json').write_text(json.dumps(self.analysis), encoding='utf-8')
        self.manifest = WorkflowManifest.model_validate(
            {
                'schemaVersion': '1.0',
                'workflowId': 'wf-minimax',
                'name': 'MiniMax H3 First Frame',
                'category': 'image-to-video',
                'description': '从 ComfyUI 导入的工作流，等待补充完整使用说明。',
                'difficulty': 'medium',
                'source': {'name': 'test', 'url': ''},
                'capabilities': ['image-to-video'],
                'recommendedFor': [],
                'notRecommendedFor': [],
                'inputs': [
                    {
                        'key': 'first-frame',
                        'label': '首帧',
                        'type': 'image',
                        'required': True,
                        'purpose': None,
                        'description': '',
                        'help': '',
                        'mapping': {},
                    }
                ],
                'parameters': [],
                'outputs': [{'key': 'video', 'type': 'video', 'format': 'mp4', 'mapping': {'nodeId': '40'}}],
                'dependencies': {
                    'models': [{'name': 'MiniMaxH3.safetensors', 'required': True}],
                    'customNodes': [{'name': 'ComfyUI-MiniMax', 'required': True}],
                },
                'runtime': {
                    'executionMode': 'serial',
                    'durationPolicy': 'dynamic',
                    'allowRetry': True,
                    'retryUnknown': False,
                    'preserveOriginalWorkflow': True,
                    'outputTimeout': 900,
                },
                'guide': {'summary': '', 'steps': [], 'promptTips': [], 'warnings': []},
            }
        )
        save_manifest(self.manifest, self.manifest_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_extract_model_options_and_basename_match(self):
        options = extract_comfy_model_options(FakeComfyClient().object_info())
        self.assertIn('models/base/MiniMaxH3.safetensors', options)
        match = match_declared_model('MiniMaxH3.safetensors', options)
        self.assertEqual(match['status'], 'PRESENT')
        self.assertEqual(match['match'], 'basename')

    def test_dependency_inventory_uses_real_object_info_node_types(self):
        with patch('backend.workflow.dependencies.discover_manifests', return_value=[(self.manifest_path, self.manifest)]):
            inventory = dependency_inventory(client=FakeComfyClient())
        self.assertTrue(inventory['connected'])
        self.assertEqual(inventory['summary']['workflows'], 1)
        self.assertEqual(inventory['summary']['ready'], 1)
        item = inventory['workflows'][0]
        self.assertEqual(item['status'], 'READY')
        self.assertEqual(item['counts']['missingModels'], 0)
        self.assertEqual(item['counts']['missingNodeTypes'], 0)

    def test_dependency_inventory_offline_is_unknown_not_missing(self):
        with patch('backend.workflow.dependencies.discover_manifests', return_value=[(self.manifest_path, self.manifest)]):
            inventory = dependency_inventory(client=OfflineComfyClient())
        self.assertFalse(inventory['connected'])
        self.assertEqual(inventory['workflows'][0]['status'], 'COMFY_OFFLINE')
        self.assertEqual(inventory['workflows'][0]['models'][0]['status'], 'UNKNOWN')
        self.assertEqual(inventory['workflows'][0]['nodeTypes'][0]['status'], 'UNKNOWN')

    def test_manifest_review_proposes_only_empty_and_high_confidence_fields(self):
        review = manifest_review_item(self.manifest_path, self.manifest)
        self.assertGreater(review['proposalCount'], 0)
        self.assertTrue(any(item.get('field') == 'description' for item in review['proposals']))
        input_proposal = next(item for item in review['proposals'] if item['type'] == 'input')
        self.assertGreaterEqual(input_proposal['confidence'], 0.80)
        self.assertEqual(input_proposal['changes']['purpose'], 'video-start-frame')
        self.assertEqual(input_proposal['changes']['mapping.nodeId'], '10')

        payload = self.manifest.model_dump(mode='json')
        payload['description'] = '人工写好的说明，不允许安全补全覆盖。'
        payload['inputs'][0]['purpose'] = 'character-reference'
        manual = WorkflowManifest.model_validate(payload)
        save_manifest(manual, self.manifest_path)
        review_manual = manifest_review_item(self.manifest_path, manual)
        self.assertFalse(any(item.get('field') == 'description' for item in review_manual['proposals']))
        input_manual = next(item for item in review_manual['proposals'] if item['type'] == 'input')
        self.assertNotIn('purpose', input_manual['changes'])

    def test_apply_safe_review_never_changes_original_json(self):
        db = Database(self.root / 'studio.sqlite3')
        db.initialize()
        with db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflows(
                    id,name,category,source,source_url,description,difficulty,original_path,
                    api_workflow_path,cover_path,manifest_json,manifest_version,enabled,
                    compatibility_status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
                """,
                (
                    self.manifest.workflowId,
                    self.manifest.name,
                    self.manifest.category,
                    'test',
                    '',
                    self.manifest.description,
                    self.manifest.difficulty,
                    str(self.original_path),
                    None,
                    None,
                    json.dumps(self.manifest.model_dump(mode='json'), ensure_ascii=False),
                    1,
                    1,
                    'NEEDS_ADAPTER',
                ),
            )
        before = self.original_path.read_bytes()
        with patch('backend.workflow.manifest_review.discover_manifests', return_value=[(self.manifest_path, self.manifest)]):
            result = apply_safe_manifest_review(db, self.manifest.workflowId)
        self.assertIsNotNone(result)
        self.assertGreater(result['applied'], 0)
        self.assertEqual(before, self.original_path.read_bytes())
        updated = load_manifest(self.manifest_path)
        self.assertEqual(updated.inputs[0].purpose, 'video-start-frame')
        self.assertEqual(updated.inputs[0].mapping.nodeId, '10')
        self.assertNotEqual(updated.description, self.manifest.description)


if __name__ == '__main__':
    unittest.main()
