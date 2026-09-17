import json
import io
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import fitz

from backend.ai.models import AdaptedStory, Episode
from backend.ai.providers.openai_compatible import OpenAICompatibleComicProvider, SEMANTIC_RULES
from backend.ai.service import ComicAiError, ComicAiService, quality_summary
from tests.test_phase1h3_ai_comic_semantic import FakeProvider, semantic


class ProbeFake(FakeProvider):
    def probe(self):
        return {'reachable': True, 'visionVerified': True, 'structuredOutputVerified': True, 'lastProbeAt': 'now'}


class Response:
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return json.dumps({'choices':[{'message':{'content':json.dumps(self.value)}}]}).encode()


class Phase1H4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.pdf = self.root/'comic.pdf'
        doc=fitz.open()
        for number in range(6):
            page=doc.new_page(width=300,height=450); page.insert_text((20,30),f'PAGE {number+1}')
        doc.save(self.pdf); doc.close()
    def tearDown(self): self.tmp.cleanup()

    def test_provider_probe(self):
        value=ComicAiService(ProbeFake(),self.root/'cache').probe()
        self.assertTrue(value['visionVerified']); self.assertTrue(value['structuredOutputVerified'])

    def test_page_image_ordering_and_prompt_rules(self):
        env={'COMIC_AI_BASE_URL':'http://127.0.0.1:9999/v1','COMIC_AI_MODEL':'vision'}
        captured={}
        def open_(request,timeout):
            captured.update(json.loads(request.data)); return Response(semantic(3))
        with patch.dict(os.environ,env,clear=True), patch('urllib.request.urlopen',side_effect=open_):
            OpenAICompatibleComicProvider().analyze_comic_pages([{'page':3,'text':'a','image':b'a'},{'page':4,'text':'b','image':b'b'}])
        content=captured['messages'][0]['content']; kinds=[x['type'] for x in content]
        self.assertEqual(kinds,['text','text','image_url','text','image_url'])
        self.assertEqual(content[1]['text'],'PAGE 3'); self.assertEqual(content[3]['text'],'PAGE 4')
        self.assertIn('Do not guess names',content[0]['text']); self.assertIn('not free story writing',SEMANTIC_RULES)
        self.assertIn('at most 4 prominent story characters', content[0]['text'])

    def test_lm_studio_probe_uses_text_but_schema_calls_stay_strict(self):
        env={'COMIC_AI_BASE_URL':'http://127.0.0.1:9999/v1','COMIC_AI_MODEL':'vision','COMIC_AI_STRUCTURED_OUTPUT':'json_schema'}
        formats=[]
        def open_(request,timeout):
            body=json.loads(request.data); formats.append(body['response_format'])
            return Response({'vision':True,'structured':True} if len(formats)==1 else semantic(1))
        with patch.dict(os.environ,env,clear=True), patch('urllib.request.urlopen',side_effect=open_):
            provider=OpenAICompatibleComicProvider(); provider.probe(); provider.analyze_comic_pages([{'page':1,'text':'','image':b'a'}])
        self.assertEqual(formats[0],{'type':'text'})
        self.assertEqual(formats[1]['type'],'json_schema'); self.assertEqual(formats[1]['json_schema']['name'],'semantic')
        self.assertEqual(formats[1]['json_schema']['schema']['properties']['characters']['maxItems'],48)

    def test_evidence_out_of_range_is_not_cached(self):
        provider=FakeProvider(); provider.analyze_comic_pages=lambda *_: semantic(6)
        service=ComicAiService(provider,self.root/'cache')
        with self.assertRaises(ComicAiError) as caught: service.analyze(self.pdf,'token',[{'page':1,'text':''}])
        self.assertEqual(caught.exception.code,'AI_EVIDENCE_OUT_OF_RANGE'); self.assertFalse(list((self.root/'cache').glob('*.json')))

    def test_real_page_cap_and_render_metrics(self):
        service=ComicAiService(FakeProvider(),self.root/'cache')
        pages=[{'page':x,'text':''} for x in range(1,6)]
        with self.assertRaises(ComicAiError): service.analyze(self.pdf,'token',pages)
        result=service.analyze(self.pdf,'token',pages[:1])
        metric=result['renderMetrics'][0]; self.assertEqual(metric['inputHeight'],1280); self.assertGreater(metric['jpegBytes'],0)
        with patch.dict(os.environ,{'COMIC_AI_IMAGE_PROFILE':'high'}):
            high=ComicAiService(FakeProvider(),self.root/'high').analyze(self.pdf,'token',pages[:1])
        self.assertEqual(high['renderMetrics'][0]['inputHeight'],1600)

    def test_quality_summary(self):
        value=semantic(1); value['characters'][0]['needsReview']=True
        summary=quality_summary(value,[1])
        self.assertEqual(summary['charactersNeedingReview'],1); self.assertEqual(summary['speakerUnknown'],1)
        self.assertEqual(summary['evidenceInvalid'],0)

    def test_debug_redaction(self):
        env={'COMIC_AI_BASE_URL':'http://127.0.0.1:9/v1','COMIC_AI_MODEL':'m','COMIC_AI_DEBUG':'true'}
        with patch.dict(os.environ,env,clear=True), patch('backend.ai.providers.openai_compatible.ROOT',self.root):
            provider=OpenAICompatibleComicProvider(); provider._debug_response('test',{'authorization':'Bearer secret','image_url':'data:image/jpeg;base64,secret','path':'D:\\private\\comic.pdf','ok':True})
        text=next((self.root/'storage/comic-analysis/debug').glob('*.json')).read_text()
        self.assertNotIn('Bearer secret',text); self.assertNotIn('base64',text); self.assertNotIn('private',text); self.assertIn('[REDACTED]',text)

    def test_retry_only_transient_and_never_invalid_json(self):
        env={'COMIC_AI_BASE_URL':'http://127.0.0.1:9/v1','COMIC_AI_MODEL':'m','COMIC_AI_MAX_RETRIES':'1'}
        with patch.dict(os.environ,env,clear=True), patch('urllib.request.urlopen',side_effect=[ConnectionError(),Response({'ok':True})]) as call:
            value=OpenAICompatibleComicProvider()._request('test',{}); self.assertEqual(value['_requestRetries'],1); self.assertEqual(call.call_count,2)
        with patch.dict(os.environ,env,clear=True), patch('urllib.request.urlopen',return_value=Response('invalid')) as call:
            with self.assertRaises(ValueError): OpenAICompatibleComicProvider()._request('test',{})
            self.assertEqual(call.call_count,1)

    def test_lm_studio_context_http_error_is_classified(self):
        env={'COMIC_AI_BASE_URL':'http://127.0.0.1:9/v1','COMIC_AI_MODEL':'m'}
        error=urllib.error.HTTPError('http://127.0.0.1:9',400,'bad request',{},io.BytesIO(b'{"error":"request exceeds available context size"}'))
        with patch.dict(os.environ,env,clear=True), patch('urllib.request.urlopen',side_effect=error):
            with self.assertRaisesRegex(RuntimeError,'AI_CONTEXT_TOO_LARGE'):
                OpenAICompatibleComicProvider()._request('test',{})

    def test_adaptation_notes_and_character_definition_stability(self):
        story=AdaptedStory.model_validate({'title':'x','logline':'x','summary':'x','characters':[],'scenes':[],'storyBeats':[],'ending':'x','learningGoals':[],'sourceEvidence':[{'sourcePage':1,'evidence':'x'}],'adaptationNotes':['simplified dialogue']})
        self.assertEqual(story.adaptationNotes,['simplified dialogue'])
        episode=Episode.model_validate({'title':'x','level':'Pre-A1','age':'3-8','duration':5,'aspectRatio':'9:16','characters':['character_01'],'characterDefinitions':[{'id':'character_01','name':'unknown','appearance':'round face','clothing':'blue coat','bodyType':'small','accessories':['cap'],'prompt':'stable child','negativePrompt':'identity drift'}],'scenes':[],'shots':[{'id':1,'title':'x','speaker':'character_01','duration':5,'imagePrompt':'stable child, park, blue coat, medium shot, standing, comic style','videoPrompt':'child waves, camera pans, leaves move, says hello, same clothes','negativePrompt':'drift','sourcePages':[1],'sourceEvidence':[{'sourcePage':1,'evidence':'wave'}],'dialogueSource':'adapted'}],'source':{'type':'comic','name':'x','fileToken':'t','pages':[1]}})
        self.assertEqual(episode.characterDefinitions[0].clothing,'blue coat'); self.assertEqual(episode.shots[0].sourcePages,[1])


if __name__ == '__main__': unittest.main()
