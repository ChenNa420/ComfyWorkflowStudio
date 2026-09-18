# Phase 1H-4 Real Vision Calibration

Phase 1H-4 keeps AI disabled by default. Configure an existing OpenAI-compatible vision endpoint explicitly before using Probe or Semantic Analysis:

- `COMIC_AI_PROVIDER=openai_compatible`
- `COMIC_AI_BASE_URL=http://127.0.0.1:.../v1`
- `COMIC_AI_MODEL=...`
- `COMIC_AI_ALLOW_REMOTE=true` only for a deliberately configured remote endpoint

The safe provider probe uses a tiny built-in image and no user comic. Semantic calibration accepts at most four real pages by default (`COMIC_AI_MAX_REAL_PAGES=4`). `COMIC_AI_IMAGE_PROFILE=standard` renders a 1280-pixel longest edge; `high` renders 1600. Debug capture is off by default. When explicitly enabled with `COMIC_AI_DEBUG=true`, sanitized JSON responses are stored under ignored `storage/comic-analysis/debug/`.

Every semantic page reference is checked against the submitted page set. Out-of-range evidence returns `AI_EVIDENCE_OUT_OF_RANGE` and is never cached. Network retries default to zero and can be set to one with `COMIC_AI_MAX_RETRIES=1`; invalid JSON is never retried.
