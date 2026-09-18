import io
import asyncio
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi import HTTPException
from fastapi import UploadFile
from starlette.datastructures import Headers

from backend import comic_story_api as comic
from backend.ai.models import Episode
from backend.ai.providers.openai_compatible import OpenAICompatibleComicProvider
from backend.ai.service import ComicAiError, ComicAiService, _render_page, merge_batches
from backend.app import create_app
from backend.workflow import pilot, runs


class BombProvider:
    name='bomb'; enabled=True
    def get_status(self): return {'provider':'bomb','enabled':True,'configured':True,'model':'x','baseUrlSafe':'','supportsVision':True,'reason':None}
    def analyze_comic_pages(self, *args, **kwargs): raise AssertionError('AI provider called by local analysis')


class EmptyProvider(BombProvider):
    def analyze_comic_pages(self, *args, **kwargs): return {}


class RemediationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.pdf=self.root/'comic.pdf'; doc=fitz.open(); page=doc.new_page(); page.insert_text((20,40),'Local words only.'); doc.save(self.pdf); doc.close()
        comic._FILE_REGISTRY.clear(); comic._ALLOWED_ROOTS.clear(); comic._register_file(self.pdf)
    def tearDown(self): self.tmp.cleanup()

    def endpoint(self, path, method='POST'):
        router=comic.comic_story_router()
        return next(r.endpoint for r in router.routes if getattr(r,'path',None)==path and method in r.methods)

    def test_local_analyze_never_calls_ai_provider(self):
        token=next(iter(comic._FILE_REGISTRY))
        with patch.object(comic,'get_comic_ai_provider',return_value=BombProvider()):
            value=self.endpoint('/api/comic-story/analyze')(comic.ComicAnalyzeRequest(token=token,startPage=1,endPage=1))
        self.assertIn('Local words only',value['textExcerpt'])

    def test_semantic_endpoint_is_ai_entrypoint(self):
        token=next(iter(comic._FILE_REGISTRY))
        with patch.object(comic,'get_comic_ai_provider',return_value=BombProvider()):
            with self.assertRaises(AssertionError): self.endpoint('/api/comic-story/semantic-analyze')(comic.ComicAnalyzeRequest(token=token,startPage=1,endPage=1))

    def test_invalid_semantic_ids_and_traversal(self):
        for value in ('../x','..\\x','C:\\x','a'*25,'ABCDEF0123456789ABCDEF01'):
            with self.assertRaises(HTTPException) as caught: comic._cache_target(value)
            self.assertEqual(caught.exception.status_code,400)

    def test_empty_semantic_rejected(self):
        service=ComicAiService(EmptyProvider(),self.root/'cache')
        with self.assertRaises(ComicAiError) as caught: service.analyze(self.pdf,'token',[{'page':1,'text':''}])
        self.assertEqual(caught.exception.code,'AI_RESPONSE_INVALID')

    def valid_episode(self):
        return {'title':'T','level':'A1','age':'6-8','duration':5,'aspectRatio':'9:16','characters':['c1'],
                'characterDefinitions':[{'id':'c1','name':'Kid'}],'scenes':[{'id':'s1'}],
                'source':{'type':'comic','name':'x.pdf','fileToken':'tok','pages':[1]},
                'shots':[{'id':1,'title':'Hi','speaker':'c1','english':'Hi','chinese':'嗨','duration':5,
                          'imagePrompt':'kid waves','videoPrompt':'medium shot, kid waves','negativePrompt':'drift',
                          'sourcePages':[1],'sourceEvidence':[{'sourcePage':1,'evidence':'wave'}],'dialogueSource':'source'}]}

    def test_episode_speaker_dialogue_and_page_validation(self):
        for mutate in ('speaker','dialogue','page'):
            value=self.valid_episode()
            if mutate=='speaker': value['shots'][0]['speaker']='missing'
            if mutate=='dialogue': value['shots'][0]['dialogueSource']='invented'
            if mutate=='page': value['shots'][0]['sourcePages']=[0]
            with self.assertRaises(Exception): Episode.model_validate(value)

    def test_local_scaffold_also_conforms_to_episode_schema(self):
        token=next(iter(comic._FILE_REGISTRY))
        value=self.endpoint('/api/comic-story/draft')(comic.ComicDraftRequest(token=token,shotCount=1,startPage=1,endPage=1))
        Episode.model_validate(value['episode'])

    def test_story_summary_aggregates_batches(self):
        base={'characters':[],'scenes':[],'dialogues':[],'plotEvents':[{'id':'e','pages':[1],'action':'x','evidence':[]}], 'props':[],'locations':[],'visualStyle':{}}
        merged=merge_batches([{**base,'storySummary':{'premise':'Start','beginning':'B','themes':['friendship'],'tone':'warm'}},
                              {**base,'storySummary':{'premise':'Middle','middle':'M','themes':['fun'],'tone':'warm'}},
                              {**base,'storySummary':{'ending':'E','resolution':'Solved','themes':['friendship'],'tone':'warm'}}])
        self.assertEqual(merged['storySummary']['beginning'],'B'); self.assertEqual(merged['storySummary']['ending'],'E')
        self.assertEqual(merged['storySummary']['themes'],['friendship','fun']); self.assertIn('Solved',merged['storySummary']['premise'])

    def test_bad_cache_recovers_and_atomic_temp_is_removed(self):
        from tests.test_phase1h3_ai_comic_semantic import FakeProvider
        service=ComicAiService(FakeProvider(),self.root/'cache')
        first=service.analyze(self.pdf,'tok',[{'page':1,'text':'x'}]); target=service.cache_dir/f"{first['id']}.json"
        target.write_text('{bad',encoding='utf-8'); second=service.analyze(self.pdf,'tok',[{'page':1,'text':'x'}])
        self.assertFalse(second['cacheHit']); self.assertFalse(target.with_suffix('.tmp').exists()); json.loads(target.read_text(encoding='utf-8'))

    def test_archive_oversize_and_compression_bomb_rejected(self):
        archive=self.root/'bad.cbz'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z: z.writestr('1.png',b'0'*(26*1024*1024))
        with self.assertRaises(RuntimeError) as caught: _render_page(archive,1)
        self.assertIn(str(caught.exception),{'COMIC_ARCHIVE_TOO_LARGE','COMIC_ARCHIVE_UNSAFE'})

    def test_remote_blocked_local_allowed_and_secret_safe(self):
        with patch.dict(os.environ,{'COMIC_AI_BASE_URL':'https://user:pw@example.com/v1','COMIC_AI_MODEL':'v','COMIC_AI_API_KEY':'secret'},clear=True):
            status=OpenAICompatibleComicProvider().get_status(); self.assertFalse(status['configured']); self.assertNotIn('secret',str(status)); self.assertNotIn('pw',str(status))
        with patch.dict(os.environ,{'COMIC_AI_BASE_URL':'http://127.0.0.1:1234/v1','COMIC_AI_MODEL':'v'},clear=True):
            status=OpenAICompatibleComicProvider().get_status(); self.assertTrue(status['configured']); self.assertTrue(status['isLocalEndpoint'])

    def test_legacy_tasks_disabled_and_material_limit(self):
        with patch.dict(os.environ,{'CWS_MAX_MATERIAL_MB':'1'}):
            app=create_app()
            legacy=next(r.endpoint for r in app.routes if getattr(r,'path',None)=='/api/tasks' and 'POST' in r.methods)
            from backend.models import GenerationTaskCreate
            with self.assertRaises(HTTPException) as caught: legacy(GenerationTaskCreate(workflowId='uncertified',inputs={},parameters={}))
            self.assertEqual(caught.exception.status_code,410); self.assertEqual(caught.exception.detail['code'],'LEGACY_TASK_API_DISABLED')
            upload=next(r.endpoint for r in app.routes if getattr(r,'path',None)=='/api/materials' and 'POST' in r.methods)
            file=UploadFile(filename='large.bin',file=io.BytesIO(b'x'*(1024*1024+1)),headers=Headers({'content-type':'application/octet-stream'}))
            with self.assertRaises(HTTPException) as caught: asyncio.run(upload(file,None))
            self.assertEqual(caught.exception.status_code,413); self.assertEqual(caught.exception.detail,'MATERIAL_TOO_LARGE')

    def test_pilot_and_run_share_creation_gate(self):
        self.assertIs(pilot.EXECUTION_CREATE_LOCK,runs.EXECUTION_CREATE_LOCK)


if __name__=='__main__': unittest.main()
