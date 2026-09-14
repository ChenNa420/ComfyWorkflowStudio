from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.db import Database
from backend.workflow import catalog


class CatalogImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / 'studio.sqlite3')
        self.db.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _workflow(self) -> dict:
        return {
            'nodes': [
                {
                    'id': 236,
                    'type': 'PixaromaLoadImageMini',
                    'title': '1. Load Image - First Frame',
                    'inputs': [],
                    'outputs': [{'name': 'image', 'type': 'IMAGE', 'links': [1]}],
                    'properties': {'cnr_id': 'ComfyUI-Pixaroma'},
                    'widgets_values': ['first.png', 'image', ''],
                },
                {
                    'id': 239,
                    'type': 'PixaromaPrompt',
                    'title': '4. Add a prompt',
                    'inputs': [],
                    'outputs': [{'name': 'text', 'type': 'STRING', 'links': []}],
                    'properties': {'cnr_id': 'ComfyUI-Pixaroma', 'promptState': {'text': 'hello'}},
                    'widgets_values': [''],
                },
            ],
            'links': [],
        }

    def test_zip_import_creates_local_package_and_deduplicates(self):
        local_root = self.root / 'workflow-packages'
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('Ep29/Minimax H3 - Image to video FF.json', json.dumps(self._workflow()))
            archive.writestr('resources/prompts.json', json.dumps({'tags': ['hello']}))

        with patch.object(catalog, 'LOCAL_WORKFLOW_ROOT', local_root):
            first = catalog.import_payload('learning.zip', buffer.getvalue(), self.db)
            second = catalog.import_payload('learning.zip', buffer.getvalue(), self.db)

        self.assertTrue(first['ok'])
        self.assertEqual(len(first['imported']), 1)
        self.assertEqual(len(first['resources']), 1)
        self.assertEqual(len(second['duplicates']), 1)
        workflow_id = first['imported'][0]['workflowId']
        self.assertTrue((local_root / workflow_id / 'original.json').is_file())
        self.assertTrue((local_root / workflow_id / 'manifest.json').is_file())
        self.assertTrue((local_root / workflow_id / 'analysis.json').is_file())
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM workflows WHERE id=?', (workflow_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['compatibility_status'], 'NEEDS_ADAPTER')


if __name__ == '__main__':
    unittest.main()
