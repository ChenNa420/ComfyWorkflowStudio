from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.models import WorkflowManifest
from backend.workflow.dependencies import execution_node_types
from backend.workflow.remediation_guides import build_remediation_guides


class Phase1G2RemediationGuideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_execution_dependency_filter_matches_converter_semantics(self):
        package = self.root / 'wf'
        package.mkdir()
        manifest_path = package / 'manifest.json'
        manifest_path.write_text('{}', encoding='utf-8')
        original = {
            'nodes': [
                {'id': 1, 'type': 'MarkdownNote', 'mode': 0, 'outputs': []},
                {'id': 2, 'type': 'MissingRuntimeNode', 'mode': 0, 'outputs': [{'links': [10]}]},
                {'id': 3, 'type': 'DetachedUiHelper', 'mode': 0, 'outputs': []},
                {'id': 4, 'type': 'DisabledMissingNode', 'mode': 2, 'outputs': [{'links': [11]}]},
            ],
            'links': [],
        }
        (package / 'original.json').write_text(json.dumps(original), encoding='utf-8')
        required, ignored = execution_node_types(
            manifest_path,
            {'nodeTypes': ['MarkdownNote', 'MissingRuntimeNode', 'DetachedUiHelper', 'DisabledMissingNode']},
            connected=True,
            object_info={},
        )
        self.assertEqual(required, ['MissingRuntimeNode'])
        ignored_map = {(item['nodeType'], item['reason']) for item in ignored}
        self.assertIn(('MarkdownNote', 'known-non-execution'), ignored_map)
        self.assertIn(('DetachedUiHelper', 'unconnected-ui-only'), ignored_map)
        self.assertIn(('DisabledMissingNode', 'mode-never'), ignored_map)

    def manifest(self, workflow_id: str) -> WorkflowManifest:
        return WorkflowManifest.model_validate(
            {
                'schemaVersion': '1.0',
                'workflowId': workflow_id,
                'name': workflow_id,
                'category': 'image-to-video',
                'description': '测试 Workflow',
                'capabilities': ['image-to-video'],
                'inputs': [],
                'parameters': [],
                'outputs': [{'key': 'video', 'type': 'video', 'format': 'mp4'}],
                'dependencies': {
                    'models': [
                        {
                            'name': 'missing-model.safetensors',
                            'required': True,
                            'path': 'models/diffusion_models/missing-model.safetensors',
                            'installUrl': 'https://example.invalid/model',
                        }
                    ],
                    'customNodes': [
                        {
                            'name': 'ComfyUI-ExampleNodes',
                            'required': True,
                            'installUrl': 'https://github.com/example/ComfyUI-ExampleNodes',
                        }
                    ],
                },
                'runtime': {'executionMode': 'serial', 'retryUnknown': False, 'preserveOriginalWorkflow': True},
            }
        )

    def test_node_guide_uses_manifest_evidence_without_auto_install(self):
        manifests = {}
        for workflow_id in ('wf-one', 'wf-two'):
            path = self.root / workflow_id / 'manifest.json'
            path.parent.mkdir()
            path.write_text('{}', encoding='utf-8')
            manifests[workflow_id] = (path, self.manifest(workflow_id))

        inventory = {
            'connected': True,
            'summary': {'ignoredNodeTypes': 2, 'ignoredNodeOccurrences': 8},
            'workflows': [
                {
                    'workflowId': 'wf-one', 'name': 'One', 'category': 'image-to-video', 'capabilities': ['image-to-video'],
                    'status': 'MISSING_DEPENDENCIES', 'models': [],
                    'nodeTypes': [{'nodeType': 'MissingNode', 'status': 'MISSING'}],
                },
                {
                    'workflowId': 'wf-two', 'name': 'Two', 'category': 'image-to-video', 'capabilities': ['image-to-video'],
                    'status': 'MISSING_DEPENDENCIES',
                    'models': [{'name': 'missing-model.safetensors', 'required': True, 'status': 'MISSING', 'modelType': 'diffusion-model'}],
                    'nodeTypes': [{'nodeType': 'MissingNode', 'status': 'MISSING'}],
                },
            ],
        }
        result = build_remediation_guides(inventory, manifests=manifests)
        node = next(item for item in result['guides'] if item['kind'] == 'NODE')
        self.assertEqual(node['affectedCount'], 2)
        self.assertEqual(node['unlockCount'], 1)
        self.assertFalse(node['writeMode'])
        self.assertEqual(node['action'], 'VERIFY_CUSTOM_NODE_PACKAGE')
        self.assertEqual(node['confidence'], 'HIGH')
        self.assertEqual(node['candidatePackages'][0]['packageName'], 'ComfyUI-ExampleNodes')
        self.assertEqual(node['sourceUrl'], 'https://github.com/example/ComfyUI-ExampleNodes')
        self.assertEqual(result['summary']['ignoredNodeOccurrences'], 8)

    def test_model_guide_exposes_declared_path_and_manifest_url_only(self):
        manifest = self.manifest('wf-model')
        path = self.root / 'wf-model' / 'manifest.json'
        path.parent.mkdir()
        path.write_text('{}', encoding='utf-8')
        inventory = {
            'connected': True,
            'summary': {},
            'workflows': [
                {
                    'workflowId': 'wf-model', 'name': 'Model', 'category': 'image-to-video', 'capabilities': ['image-to-video'],
                    'status': 'MISSING_DEPENDENCIES',
                    'models': [{'name': 'missing-model.safetensors', 'required': True, 'status': 'MISSING', 'modelType': 'diffusion-model'}],
                    'nodeTypes': [],
                }
            ],
        }
        result = build_remediation_guides(inventory, manifests={'wf-model': (path, manifest)})
        guide = result['guides'][0]
        self.assertEqual(guide['kind'], 'MODEL')
        self.assertEqual(guide['action'], 'VERIFY_MODEL_SOURCE')
        self.assertEqual(guide['declaredPaths'][0]['declaredPath'], 'models/diffusion_models/missing-model.safetensors')
        self.assertEqual(guide['sourceUrls'][0]['url'], 'https://example.invalid/model')
        self.assertFalse(guide['writeMode'])

    def test_offline_never_returns_install_guidance(self):
        result = build_remediation_guides({'connected': False, 'summary': {}, 'workflows': []})
        self.assertFalse(result['connected'])
        self.assertEqual(result['guides'], [])
        self.assertEqual(result['blocked'], 0)


if __name__ == '__main__':
    unittest.main()
