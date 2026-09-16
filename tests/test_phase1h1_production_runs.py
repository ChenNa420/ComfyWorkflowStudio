import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.db import Database
from backend.models import GenerationTaskCreate
from backend.workflow.pilot import PilotRejected
from backend.workflow.runs import create_run, list_runs, rerun, run_detail, run_schema


class Phase1H1ProductionRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / 'runs.sqlite3')
        self.db.initialize()
        self.manifest = {
            'schemaVersion':'1.0','workflowId':'run-wf','name':'Production','category':'image-to-video',
            'inputs':[{'key':'image','label':'Image','type':'image','required':True}],
            'parameters':[{'key':'seed','label':'Seed','type':'seed','default':-1}],
        }
        with self.db.connect() as conn:
            conn.execute("INSERT INTO workflows(id,name,category,original_path,manifest_json,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now'))", ('run-wf','Production','image-to-video','missing.json',json.dumps(self.manifest)))

    def tearDown(self): self.tmp.cleanup()
    def certified(self, *args, **kwargs): return {'workflowId':'run-wf','status':'CERTIFIED','dependencyStatus':'READY','sourceFormat':'API'}

    @patch('backend.workflow.pilot.preflight_detail')
    def test_schema_is_certified_and_manifest_driven(self, preflight):
        preflight.side_effect=self.certified
        value=run_schema(self.db,'run-wf')
        self.assertTrue(value['allowed']);self.assertTrue(value['requiredInputsPending']);self.assertEqual(value['manifest']['inputs'][0]['type'],'image')

    @patch('backend.workflow.runs.start_task')
    @patch('backend.workflow.pilot.preflight_detail')
    def test_create_has_authorization_event_and_starts_once(self, preflight, start):
        preflight.side_effect=self.certified
        task=create_run(self.db,'run-wf',GenerationTaskCreate(workflowId='wrong',inputs={'image':'a.png'}))
        start.assert_called_once_with(self.db,task)
        with self.db.connect() as conn:
            row=conn.execute("SELECT event FROM generation_task_events WHERE task_id=? AND event='RUN_AUTHORIZED'",(task,)).fetchone()
        self.assertIsNotNone(row)

    @patch('backend.workflow.pilot.preflight_detail')
    def test_required_input_rejected_before_task(self, preflight):
        preflight.side_effect=self.certified
        with self.assertRaises(PilotRejected): create_run(self.db,'run-wf',GenerationTaskCreate(workflowId='run-wf'))
        with self.db.connect() as conn: self.assertEqual(conn.execute('SELECT COUNT(*) c FROM generation_tasks').fetchone()['c'],0)

    @patch('backend.workflow.runs.start_task')
    @patch('backend.workflow.pilot.preflight_detail')
    def test_double_submit_is_blocked(self, preflight, start):
        preflight.side_effect=self.certified
        create_run(self.db,'run-wf',GenerationTaskCreate(workflowId='run-wf',inputs={'image':'a'}))
        with self.assertRaises(PilotRejected) as caught: create_run(self.db,'run-wf',GenerationTaskCreate(workflowId='run-wf',inputs={'image':'b'}))
        self.assertEqual(caught.exception.code,'RUN_ACTIVE')

    @patch('backend.workflow.runs.start_task')
    @patch('backend.workflow.pilot.preflight_detail')
    def test_history_detail_and_rerun_create_new_task(self, preflight, start):
        preflight.side_effect=self.certified
        first=create_run(self.db,'run-wf',GenerationTaskCreate(workflowId='run-wf',inputs={'image':'a'}))
        with self.db.connect() as conn: conn.execute("UPDATE generation_tasks SET status='SUCCEEDED' WHERE id=?",(first,))
        second=rerun(self.db,first)
        self.assertNotEqual(first,second);self.assertEqual(len(list_runs(self.db,'run-wf')),2);self.assertEqual(run_detail(self.db,second)['inputs']['image'],'a')


if __name__ == '__main__': unittest.main()
