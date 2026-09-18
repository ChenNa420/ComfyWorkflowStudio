import tempfile
import unittest
from pathlib import Path

import fitz
from fastapi import HTTPException

from backend import comic_story_api as comic


class Phase1H2ComicStoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.collection = self.root / 'Beano'
        self.collection.mkdir()
        self.pdf = self.collection / 'sample.pdf'
        doc = fitz.open()
        for text in ['Hello comic world.', 'Benny finds a blue ball.', 'The friends go home.']:
            page = doc.new_page(width=320, height=480)
            page.insert_text((36, 72), text)
        doc.save(self.pdf)
        doc.close()
        comic._FILE_REGISTRY.clear()
        comic._ALLOWED_ROOTS.clear()
        self.router = comic.comic_story_router()
    def tearDown(self):
        self.tmp.cleanup()

    def endpoint(self, path: str, method: str):
        for route in self.router.routes:
            if getattr(route, 'path', None) == path and method in getattr(route, 'methods', set()):
                return route.endpoint
        self.fail(f'endpoint not found: {method} {path}')

    def test_scan_requires_scanned_root_before_issue_listing(self):
        issues = self.endpoint('/api/comic-story/issues', 'POST')
        with self.assertRaises(HTTPException) as caught:
            issues(comic.ComicSourceRequest(path=str(self.collection)))
        self.assertEqual(caught.exception.status_code, 403)

    def test_scan_issue_preview_and_analysis(self):
        scan = self.endpoint('/api/comic-story/scan', 'POST')
        issues = self.endpoint('/api/comic-story/issues', 'POST')
        page = self.endpoint('/api/comic-story/page/{token}/{page_number}', 'GET')
        analyze = self.endpoint('/api/comic-story/analyze', 'POST')
        scanned = scan(comic.ComicScanRequest(path=str(self.root)))
        self.assertEqual(scanned['count'], 1)
        result = issues(comic.ComicSourceRequest(path=str(self.collection), limit=10))
        self.assertEqual(result['count'], 1)
        issue = result['issues'][0]
        self.assertEqual(issue['pageCount'], 3)
        preview = page(issue['token'], 1, True)
        self.assertEqual(preview.media_type, 'image/jpeg')
        value = analyze(comic.ComicAnalyzeRequest(token=issue['token'], startPage=1, endPage=2))
        self.assertEqual(value['selectedPages'], [1, 2])
        self.assertIn('Hello comic world.', value['textExcerpt'])

    def test_draft_uses_source_pages_and_requires_ai_enrichment(self):
        scan = self.endpoint('/api/comic-story/scan', 'POST')
        issues = self.endpoint('/api/comic-story/issues', 'POST')
        draft = self.endpoint('/api/comic-story/draft', 'POST')
        scan(comic.ComicScanRequest(path=str(self.root)))
        issue = issues(comic.ComicSourceRequest(path=str(self.collection)))['issues'][0]
        value = draft(comic.ComicDraftRequest(token=issue['token'], title='Test', shotCount=6, startPage=1, endPage=3))
        self.assertTrue(value['requiresAiEnrichment'])
        self.assertEqual(value['episode']['title'], 'Test')
        self.assertEqual(len(value['episode']['shots']), 6)
        self.assertTrue(all(1 <= shot['sourcePage'] <= 3 for shot in value['episode']['shots']))
        self.assertEqual(value['provider'], {'name': 'disabled', 'enabled': False})
        self.assertEqual(value['episode']['level'], 'Pre-A1')
        self.assertEqual(value['episode']['characters'], [])
        self.assertIn('sourceEvidence', value['episode']['shots'][0])

    def test_disabled_provider_returns_pending_semantics(self):
        scan = self.endpoint('/api/comic-story/scan', 'POST')
        issues = self.endpoint('/api/comic-story/issues', 'POST')
        analyze = self.endpoint('/api/comic-story/analyze', 'POST')
        scan(comic.ComicScanRequest(path=str(self.root)))
        issue = issues(comic.ComicSourceRequest(path=str(self.collection)))['issues'][0]
        value = analyze(comic.ComicAnalyzeRequest(token=issue['token'], startPage=1, endPage=1))
        self.assertTrue(value['requiresAiEnrichment'])
        self.assertEqual(value['provider']['name'], 'disabled')
        self.assertEqual(value['semanticAnalysis']['status'], 'pending')
        self.assertEqual(value['semanticAnalysis']['characters'], [])

    def test_corrupt_pdf_is_isolated_to_one_issue(self):
        (self.collection / 'broken.pdf').write_bytes(b'not a pdf')
        scan = self.endpoint('/api/comic-story/scan', 'POST')
        issues = self.endpoint('/api/comic-story/issues', 'POST')
        scan(comic.ComicScanRequest(path=str(self.root)))
        values = issues(comic.ComicSourceRequest(path=str(self.collection)))['issues']
        self.assertEqual(len(values), 2)
        broken = next(item for item in values if item['filename'] == 'broken.pdf')
        self.assertIsNone(broken['pageCount'])


if __name__ == '__main__':
    unittest.main()
