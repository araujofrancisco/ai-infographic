# AGENTS.md

## Project
AI infographic generator. FastAPI app in `app/`: Ollama generates infographic
content as JSON (Pydantic schema), ComfyUI renders ONE portrait SDXL image
(1024x1448) that becomes the full-page background, `renderer.py` overlays the
text on it and composites an A4 SVG/PNG/PDF (cairosvg).
`pytest` suite + `ruff` safety checks + GitHub Actions CI (see
`scripts/verify.sh`). Local git repo, no remote (`.gitignore` excludes `.env`,
`comfyui/`, `output/`, `projects/`, `tasks/`).

## Running
- `docker compose up --build` starts `comfyui` (port 8188, requires NVIDIA GPU)
  and `infographic` (FastAPI, port `APP_PORT`, default 8090).
- `.env` at repo root sets `OLLAMA_URL`, `OLLAMA_MODEL` (gemma4:12b),
  `COMFYUI_URL`, `COMFYUI_CHECKPOINT` (sd_xl_base_1.0.safetensors), `APP_PORT`.
  Optional tunables (defaults in compose): `OLLAMA_MAX_ATTEMPTS=3`,
  `COMFYUI_MAX_WAIT_SECONDS=1200`, `TASK_TTL_SECONDS=1800`,
  `TASKS_DIR=/app/tasks`, `MAX_QUEUED_PER_KIND=2`,
  `PROJECT_RETENTION_SECONDS=2592000` (30d, 0 disables artifact cleanup),
  `CLEANUP_INTERVAL_SECONDS=3600`.
  Compose reads `.env`; the app does NOT load `.env` itself (no python-dotenv).
  On boot the app fails fast if the `OUTPUT_DIR`/`PROJECTS_DIR`/`TASKS_DIR`
  dirs are missing or unwritable.
- Local dev (no Docker): from `app/` run `uvicorn main:app --port 8080` with
  env vars pointing at a running Ollama (default `host.docker.internal:11434`)
  and ComfyUI. Generation is slow (Ollama 600s timeout, ComfyUI capped at
  `COMFYUI_MAX_WAIT_SECONDS`).

## Architecture
- Long-running work is async, NOT awaited in the route. `POST /generate-content`
  and `POST /generate-infographic` start an in-process task via `app/tasks.py`
  (`TaskManager`, `asyncio.create_task`) and immediately return `working.html`,
  which polls `GET /tasks/{id}/status` (exponential backoff, 2s->5s) and
  redirects to `/review/{pid}` or `/result/{pid}` on success, or `/tasks/{id}`
  (error page) on failure.
  In-memory state; lost on restart (fine for single-worker compose). Tasks have
  a per-kind semaphore (one running + `MAX_QUEUED_PER_KIND` queued), timestamps,
  a `progress {current,total,message}` dict, hard cancel (`cancel()` aborts the
  underlying asyncio task mid-await, plus a cooperative check via the progress
  callback as a fallback), and lazy TTL prune (`TASK_TTL_SECONDS`) of finished
  tasks. Workers take `async def worker(set_progress)`.
- Task state is persisted in a JSONL journal (`TASKS_DIR/journal.jsonl`,
  `app/task_store.py`). `TaskManager` journals every transition (created /
  started / terminal), never per-tick progress. On boot `main.py` calls
  `task_manager.restore()`, which replays finished tasks into memory (status
  pages + the `/activity` feed survive restarts) and marks any orphaned
  pending/running task as `failed` with "interrupted by restart" so the
  `working.html` poller gets a terminal state instead of a 404. The journal is
  git-ignored and survives process death; journal writes degrade gracefully if
  `TASKS_DIR` is unwritable.
- `main.py` is a thin app factory (static mount + three `APIRouter`s + a
  `lifespan` that starts/stops `app/cleanup.py`'s `ProjectJanitor` and calls
  `task_manager.restore()`). The janitor is a background loop (every
  `CLEANUP_INTERVAL_SECONDS`) that deletes `projects/<id>` + `output/<id>` for
  projects older than `PROJECT_RETENTION_SECONDS` (aged by the stored
  `updated_at` timestamp, falling back to file `mtime` for legacy projects) and
  not referenced by a running task (`TaskManager.active_project_ids()`);
  `PROJECT_RETENTION_SECONDS=0` disables it. Task lifecycle events
  (start/success/failure/cancel duration) and Ollama retry attempts are logged
  with the task id. `app/routes_ui.py` (pages + save-content + generate + file
  serving), `app/routes_tasks.py` (status + error page) and `app/routes_library.py`
  (library + delete + thumbnail + activity) hold all HTTP. Business logic lives
  in `app/services.py` (`ContentService`, `RenderingService`), storage in
  `app/storage.py` (`ProjectRepository` writes `projects/<uuid>/project.json`
  with `created_at`/`updated_at` timestamps and exposes `list_projects()`,
  `OutputStore` resolves `output/<uuid>/infographic.*` and guards path
  traversal), workers in `app/workers.py`.
- The library (`GET /projects`) is a thumbnail card grid over
  `ProjectRepository.list_projects()`, showing draft vs rendered status
  (rendered = all of svg/png/pdf exist in `output/`), with actions to open,
  download the PDF, or hard-delete (`POST /projects/{id}/delete` refuses a 409
  while an active task references the project). It accepts `q` (case-insensitive
  filter on topic/audience/style) and `page` (paginated at `PAGE_SIZE`, default
  12). `GET /projects/{id}/thumbnail`
  serves the rendered `infographic.png` or the raw `page.png` via a
  uuid-guarded resolver. `GET /activity` renders the tail of the task journal
  with status/duration and links back to projects. A `_nav.html` partial
  (New / Library / Activity) is included on every page.
- Content worker -> `ContentService.create_content` -> `OllamaClient` (corrective
  retry up to `OLLAMA_MAX_ATTEMPTS` on invalid JSON/schema) -> project saved.
  Infographic worker -> `RenderingService.generate()` -> one `ComfyUIClient`
  portrait image (`projects/<id>/page.png`) -> `renderer.py` (offloaded via
  `asyncio.to_thread`, so cairosvg never blocks the event loop). An existing
  non-empty `page.png` is REUSED (resume); pass `force=True` to regenerate it
  (the only way to get a new illustration). After (re)use, `_prepare_page_image`
  (Pillow) Gaussian-blurs the left text column of `page.png` (0-42% width solid,
  fading to none by 56%) so text-like artifacts the model sometimes draws can
  never survive inside the overlaid-text zone; the right side keeps full detail.
- `GET /result/{project_id}` mirrors `/review/{project_id}` and checks the
  output files exist on disk before rendering `result.html`.
- `app/workflows/illustration_api.json` is the ComfyUI API workflow.
  `comfyui_client.py` hardcodes its node IDs (checkpoint=1, positive=3,
  negative=4, ksampler=5, latent=9, save_image=13) and sets the latent to
  `IMAGE_WIDTH`x`IMAGE_HEIGHT` (1024x1448 portrait). `build_workflow` also
  overrides the checkpoint loader's `ckpt_name` from `COMFYUI_CHECKPOINT`
  (it is honored, not decorative). Editing the workflow means re-syncing those
  constants.
- `renderer.py` auto-fits: `_fit_scale` shrinks fonts/padding (min
  scale 0.6) so all sections fit one A4 page. `build_svg(content, paths)`
  fits by default; pass `scale=` to pin it. `build_svg` rejects an empty
  `image_paths` list. The title and subtitle are wrapped to at most 2 lines
  each (ellipsis) via `_plan_header`/`_cap_lines`, and the measured header
  height shifts the section blocks down. Layout is a true "poster": the
  first image in `paths` is the full-bleed page illustration (cover-cropped),
  and the text is set directly INTO the artwork with NO card boxes. A light
  `pageScrim` unifies the art, and a left `textScrim` (horizontal dark
  gradient that fades rightward) creates the legible text zone over the left
  ~42% column, which the ComfyUI prompt keeps calm (subject on the right/
  center, open left area). All text is white with a soft drop shadow: bold
  title + lighter subtitle, then one block per section with an accent-colored
  inline `NN` number + bold title, italic low-opacity description, bullets
  with accent dots and a bold keyword prefix (`_bullet_prefix` splits at the
  first `:`), the last bullet as an accent "Example:" callout (italic, with a
  left accent bar instead of a dot; the word is only injected when the bullet
  doesn't already mention "example"), and a thin white divider with an accent
  tile between sections. The four themes (Teal/Aqua, Slate/Steel Blue, Deep
  Blue/Muted Orange, Terracotta/Amber) cycle for the numbers/dots/dividers.
- The review page is EDITABLE: fields bind to the `InfographicContent` schema,
  `static/review.js` serializes the DOM to `content_json` and POSTs to
  `/save-content?json=1` (returns `{"ok":true}` / `400 {"ok":false,"error":...}`
  so edits are never lost on validation failure). "Generate infographic" saves
  first, then submits the hidden generate form (`force-regen` checkbox
  regenerates `page.png`).

## Verification
- `scripts/verify.sh` runs, in order: `pytest` (unit + component suite in
  `tests/`), `ruff check` (safety rules only: pyflakes `F` + syntax `E9`; the
  deliberate one-arg-per-line style is NOT auto-formatted), and the dependency-
  light `python3 smoke_test.py`. GitHub Actions runs the same steps
  (`.github/workflows/ci.yml`, dormant until a remote is added).
- pytest `tests/` covers storage timestamps + `list_projects()` (ordering,
  corrupt/uuid filtering, mtime fallback), the task journal lifecycle and
  `TaskManager.restore()` (terminal replay + interrupted-as-failed), renderer
  wrap/fit boundaries + header wrap/empty-image guard, `services.py`
  (page-prompt motifs, `create_content`, `generate` resume vs `force`), UI/task
  routes via `TestClient` (queue-full, `save-content` JSON 400/404, error-page
  retry forms), library/delete/thumbnail/activity/search/pagination routes,
  and a **ComfyUI workflow contract test** that asserts every
  node-ID constant in `comfyui_client.py` exists in `illustration_api.json`
  with the expected type and wiring and that `build_workflow` applies
  `COMFYUI_CHECKPOINT` (guards the "edit workflow, re-sync constants" foot-gun).
- Dependency-light checks (no venv needed): `python3 smoke_test.py` - AST-parses
  every module, asserts `ComfyUIClient` methods are inside the class, runs
  `renderer.build_svg()` with duck-typed content (stubs pydantic if missing),
  exercises `TaskManager` with fake workers (success/failure/progress, queue
  cap, hard + cooperative cancel, TTL prune, serialization), checks `_fit_scale`,
  and exercises `ProjectJanitor.cleanup_once` (stale vs fresh vs active vs
  disabled).
- Full check inside the real image (has pydantic/httpx/cairosvg + libcairo):
  `docker build -t infographic-smoke ./app && docker run --rm -v "$(pwd)/smoke_test.py:/smoke_test.py:ro" -w /app infographic-smoke python /smoke_test.py --full`.
  This imports the whole app, builds a ComfyUI workflow, renders a real
  SVG/PNG/PDF from the Pydantic models, checks `_status_error` detail extraction
  and the Ollama corrective-retry loop, and (via a live uvicorn subprocess on
  port 8092 with `OLLAMA_URL` pointed at a dead port) drives the async queue:
  POST -> `working.html` -> poll status -> failed -> error page, plus a
  `save-content` round trip (valid -> persisted, invalid -> 400).
  Do NOT use `starlette.testclient.TestClient` for the async flow: it does not
  pump `asyncio.create_task` background tasks created inside handlers.

## Fixed bugs (verified 2026-08)
- `app/comfyui_client.py` was structurally broken: `build_workflow` sat at
  module level and `generate_image` et al. were unreachable code nested inside
  it. Now all methods are proper class methods (`build_workflow` deep-copies
  the workflow). ComfyUI calls are wrapped in `GenerationError`
  (`app/exceptions.py`) with the server error body surfaced.
- `app/renderer.py` `PAGE_HEIGTH` typo fixed to `PAGE_HEIGHT`. Card heights are
  now computed from measured text instead of a fixed 480px, so long bullet
  lists no longer overflow their cards.
- Static files were never served (no mount) - `app/main.py` now mounts
  `/static`; `style.css` and `app.js` are served.
- The failed-infographic task page 500'd when the worker died before setting
  `task.project_id` (`_load_project_content(None)`). The page now falls back to
  the task's stored `form["project_id"]`, and `_load_project_content` guards
  against `None`.
- Ollama httpx timeout was 300s (too short for 12B cold loads + single-slot
  queueing); raised to 600s with distinct connect/timeout messages. `TaskManager`
  now serializes tasks per `kind` (one content / one infographic at a time).
- ComfyUI wait was unbounded (`timeout=None` + `while True` polling) so a hung
  prompt blocked the infographic slot forever. `_wait_for_completion` now enforces
  `COMFYUI_MAX_WAIT_SECONDS`, handles connection loss, and surfaces the node
  execution error detail from `status["messages"]` instead of a generic message.
- `render_infographic` (cairosvg) ran synchronously inside the event loop,
  freezing all HTTP for minutes; it is now offloaded via `asyncio.to_thread`.
- Image generation was all-or-nothing: a failure at section N forced a full
  re-render. `RenderingService.generate()` now reuses the existing non-empty
  `page.png` (resume) unless `force=True`.
- The review page's "edit content" feature was dead: `review.html` had no
  inputs and nothing POSTed to `/save-content`. Fields now bind to the
  `InfographicContent` schema, `static/review.js` serializes edits, and
  `/save-content?json=1` returns `{"ok":true}` / `400 {"ok":false,...}` so
  edits survive validation failures. Failed tasks get "cancelled" status and a
  clear message; `working.html` stops polling with an actionable error when a
  task 404s (server restart) instead of spinning forever.

## Style & gotchas
- Match the existing call style: multi-line calls with each arg on its own line,
  no docstrings, Pydantic v2 (`model_validate`).
- `cairosvg` is imported lazily inside `render_infographic` (not at module top)
  so `build_svg()` can be tested without libcairo.
- Task failure pages reuse `index.html`/`review.html` with an `error` banner
  (form values are echoed back from the task's stored `form`) plus a one-click
  retry form (`_retry.html` partial) that re-submits the stored form via
  `data-loading`. `working.html`
  JS lives inline; `static/app.js` handles the form submit spinner on
  index/result pages; `static/review.js` owns review-page save/regen logic;
  `static/library.js` owns the library delete flow. A `_nav.html` partial is
  included on every page; pass `active` in the context to highlight a tab.
- `comfyui/` is a ~6.6G mounted install; in-container files can be root-owned
  mode 600 (e.g. `comfyui/workflows/illustration.json`) - the app never reads them.
- `output/`, `projects/` and `tasks/` are runtime data dirs (compose volumes)
  and git-ignored.
- Image prompts aggressively forbid text/letters (illustrations sit inside a
  text infographic); keep that in prompts.
