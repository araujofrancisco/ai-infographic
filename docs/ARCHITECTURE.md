# Architecture

How the AI Infographic Generator works under the hood. This is the technical
reference; for running it see [Deployment](DEPLOYMENT.md), for the HTTP surface
see [API](API.md).

## Contents

- [Component map](#component-map)
- [Request flow](#request-flow)
- [Task lifecycle](#task-lifecycle)
- [Task journal and restart recovery](#task-journal-and-restart-recovery)
- [Content generation pipeline](#content-generation-pipeline)
- [Rendering pipeline](#rendering-pipeline)
- [Poster layout](#poster-layout)
- [Storage layout](#storage-layout)
- [Project janitor](#project-janitor)
- [ComfyUI workflow contract](#comfyui-workflow-contract)

## Component map

All Python lives in `app/`. The app is a FastAPI process exposing a small
HTML UI and a few JSON endpoints; long-running work is async and in-process.

| Module | Responsibility |
| --- | --- |
| `main.py` | App factory. Mounts `/static`, includes the three routers, runs the lifespan: ensures data dirs exist, restores tasks from the journal, starts/stops the janitor. |
| `config.py` | `Settings` from environment (see README configuration table). |
| `models.py` | Pydantic v2 schemas: `InfographicContent` (title, subtitle, `sections[3..8]`) and `Section` (title, short description, `bullet_points[2..5]`, `visual_description`). |
| `routes_ui.py` | Pages + generation endpoints: `/`, `/generate-content`, `/save-content`, `/review/{id}`, `/result/{id}`, `/generate-infographic`, `/files/{id}/{name}`. |
| `routes_tasks.py` | `GET /tasks/{id}/status` (JSON) and `GET /tasks/{id}` (error page). |
| `routes_library.py` | `/projects` (library), `/projects/{id}/thumbnail`, `/projects/{id}/delete`, `/activity`. |
| `services.py` | `ContentService.create_content` / `save_content`; `RenderingService.generate`. |
| `workers.py` | `content_worker`, `infographic_worker` — thin bridges from the task system to the services. |
| `tasks.py` | `TaskManager` — queue, lifecycle, cancellation, TTL prune, journaling. |
| `task_store.py` | `TaskStore` — JSONL journal (append/read/recent/delete). |
| `storage.py` | `ProjectRepository` (project JSON CRUD, listing), `OutputStore` (output file paths + traversal guard). |
| `cleanup.py` | `ProjectJanitor` — background retention sweep. |
| `ollama_client.py` | `OllamaClient` — LLM chat with corrective retry on invalid JSON/schema. |
| `comfyui_client.py` | `ComfyUIClient` — submits the SDXL workflow, polls history, downloads the image. |
| `renderer.py` | Pure SVG builder + `cairosvg` raster/PDF export. |
| `exceptions.py` | `GenerationError` — user-facing task failure message. |
| `templates/`, `static/` | Jinja2 pages and page JS/CSS. |
| `workflows/illustration_api.json` | ComfyUI API workflow (node IDs are a contract — see below). |

## Request flow

Two independent, asynchronously run jobs make up a generation. Neither is
awaited in the route: the handler starts a task via `TaskManager.start` and
immediately returns `working.html`, which polls `GET /tasks/{id}/status` with
exponential backoff (2s → 5s) and redirects on success or failure.

**Content job** (`kind="content"`):

```
POST /generate-content (topic, audience, style, section_count)
  -> task_manager.start(content_worker)
  -> ContentService.create_content
     -> OllamaClient.generate_content   (schema-validated, retry loop)
  -> ProjectRepository.create_project   (projects/<uuid>/project.json)
  -> result {project_id}
  -> redirect to /review/{id}
```

**Infographic job** (`kind="infographic"`):

```
POST /generate-infographic (project_id, force)
  -> task_manager.start(infographic_worker)
  -> RenderingService.generate
     -> ComfyUIClient.generate_image    (SDXL 1024x1448 -> projects/<id>/page.png)
     -> _prepare_page_image             (Pillow: blur left text column)
     -> render_infographic (asyncio.to_thread)
        -> build_svg -> cairosvg svg/png/pdf in output/<id>/
  -> result {project_id}
  -> redirect to /result/{id}
```

The review page is **editable**: fields bind to `InfographicContent`, and
`static/review.js` serializes the DOM to `content_json` and POSTs to
`/save-content?json=1` (returns `{"ok":true}` / `400 {"ok":false,"error":...}`)
so edits survive validation failures. "Generate infographic" saves first, then
submits the hidden generate form; the `force` flag regenerates `page.png`.

## Task lifecycle

`TaskManager` (`tasks.py`) holds tasks in memory keyed by UUID.

- **Per-kind serialization.** One `asyncio.Semaphore(1)` per kind
  (`content`, `infographic`) guarantees a single running worker per kind.
- **Bounded queue.** `can_start` counts pending + running per kind; starting is
  allowed while `active < 1 + MAX_QUEUED_PER_KIND`. Otherwise `QueueFullError`
  is raised and the UI shows a "queue is full" message.
- **States:** `pending → running → succeeded | failed | cancelled`.
- **Progress.** Workers receive a `set_progress(current, total, message)`
  callback. It also acts as a *cooperative cancel* check: if the task was
  cancelled, it raises `TaskCancelled`, which is caught and recorded as
  `cancelled`.
- **Hard cancel.** `TaskManager.cancel` sets `task.cancelled = True` and, if
  the coroutine is not done, calls `.cancel()` on it (aborts mid-await).
- **TTL prune.** `prune()` drops finished tasks older than
  `TASK_TTL_SECONDS`. It runs lazily on `start`/`get`.
- **Result/error.** `succeeded` stores `result`; `failed` stores
  `error` (from `GenerationError.message`, or a generic "check the server logs"
  message for unexpected exceptions).

Task lifecycle transitions are logged with the task id.

## Task journal and restart recovery

- `TaskStore` appends a **snapshot per lifecycle transition** (created /
  started / terminal) to `tasks/journal.jsonl` as JSONL. Progress ticks are
  never written, so the journal stays small.
- Snapshots include `form`, `project_id`, `result`, `status`, timestamps, and a
  `ts` wall-clock time. Writes degrade gracefully (logged, not fatal) if the
  tasks dir is unwritable.
- On boot (`main.py` lifespan) `task_manager.restore()`:
  - Keeps the **latest snapshot per task id**.
  - **Terminal** tasks are replayed into memory, so status pages and the
    `/activity` feed survive restarts.
  - **Pending/running** tasks become `failed` with
    `INTERRUPTED_MESSAGE` ("The server restarted while this task was running.
    Please start it again."), giving the `working.html` poller a terminal state
    instead of a 404.

Because task state is in-memory, single-worker is the supported topology (see
[Deployment](DEPLOYMENT.md#production-notes)).

## Content generation pipeline

`OllamaClient.generate_content` (`ollama_client.py`):

1. Builds a system prompt (audience/style/section count) + user prompt (topic).
2. Calls `POST {OLLAMA_URL}/api/chat` with `stream: false`,
   `temperature: 0`, and `format: InfographicContent.model_json_schema()` so
   Ollama attempts structured output.
3. For up to `OLLAMA_MAX_ATTEMPTS` attempts:
   - Parse JSON; on `JSONDecodeError` or Pydantic `ValidationError`, append
     corrective messages ("Your previous response was rejected…") and retry.
   - Return the validated `InfographicContent` on success.
4. Fails with a user-facing `GenerationError` after the last attempt.

The httpx client has a **fixed 600 s timeout** with distinct messages for
connect errors vs timeouts.

`ContentService.create_content` then persists the project via
`ProjectRepository.create_project`, which writes
`projects/<uuid>/project.json` with `id`, `topic`, `audience`, `style`,
`content`, `created_at`, and `updated_at` (UTC ISO).

## Rendering pipeline

`RenderingService.generate` (`services.py`):

1. Loads the project and validates `content`.
2. **Resume:** if `page.png` exists, is non-empty, and `force` is falsy, the
   existing illustration is reused — this is the only way to skip a slow SDXL
   run. `force=True` regenerates it.
3. Otherwise builds an illustration prompt from the project's topic/style and
   calls `ComfyUIClient.generate_image` (SDXL, 1024×1448 portrait). The
   per-section `visual_description` fields are woven in as "section motifs"
   (`_section_motifs`, deduped/capped) so the art echoes the content. The
   prompt keeps the right/center busy and the left ~45% calm for text.
4. `_prepare_page_image` (Pillow, offloaded to a thread) Gaussian-blurs the
   left text column of `page.png` (solid to 42% width, fading to none by 56%)
   so text-like artifacts can never survive inside the overlaid-text zone.
5. `render_infographic` (via `asyncio.to_thread` so cairosvg never blocks the
   event loop) writes `output/<id>/infographic.{svg,png,pdf}`:
   - `build_svg` produces a single SVG document with the illustration embedded
     as base64.
   - `cairosvg.svg2png` (2489×3508) and `cairosvg.svg2pdf` produce the exports.

### ComfyUI client

`ComfyUIClient` (`comfyui_client.py`):

- Loads `app/workflows/illustration_api.json` at construction; `build_workflow`
  deep-copies it and injects the prompt, negative prompt, random seed,
  filename prefix, and latent `width`/`height` (1024×1448).
- `generate_image` POSTs to `{COMFYUI_URL}/prompt` with **no client-side
  timeout** (generation can run for minutes), then polls
  `/history/{prompt_id}` every second until the status shows
  `status_str == "success"`, surfacing node execution errors from
  `status["messages"]` (execution_error / execution_interrupted), honoring
  `COMFYUI_MAX_WAIT_SECONDS`, and raising `GenerationError` on connection
  loss or error responses.
- Downloads the first output image via `/view` and writes it to
  `projects/<id>/page.png`.

## Poster layout

`renderer.py` composes a true "poster" (no card boxes):

- A4 portrait canvas (`PAGE_WIDTH=2489`, `PAGE_HEIGHT=3508`), all text set
  directly *into* the full-bleed artwork.
- A light `pageScrim` (vertical gradient) unifies the art; a left `textScrim`
  (horizontal dark gradient, fading rightward) creates the legible zone over
  the left ~42% column.
- Title (bold) + subtitle (lighter), wrapped to at most 2 lines each with an
  ellipsis (`_plan_header`/`_cap_lines`), the measured header height shifting
  the section blocks down; then one block per section with an
  accent-colored inline `NN` number + bold title, an italic low-opacity
  description, bullets with accent dots and a bold keyword prefix
  (`_bullet_prefix` splits at the first `:`), the last bullet rendered as an
  accent "Example:" callout (italic, left accent bar, the word only injected if
  the bullet doesn't already mention "example"), and a thin white divider with
  an accent tile between sections.
- Four themes cycle per section (Teal/Aqua, Slate/Steel Blue, Deep
  Blue/Muted Orange, Terracotta/Amber).
- **Auto-fit:** `_fit_scale` measures text via approximate character wrapping
  and shrinks fonts/padding (min scale 0.6, step 0.05) until all sections fit
  one page. `build_svg` fits by default; pass `scale=` to pin it, and it
  rejects an empty `image_paths` list.

## Storage layout

```
projects/<uuid>/project.json     # content + metadata (git-ignored)
projects/<uuid>/page.png         # SDXL background illustration (git-ignored)
output/<uuid>/infographic.svg    # final SVG (git-ignored)
output/<uuid>/infographic.png    # final PNG
output/<uuid>/infographic.pdf    # final PDF
tasks/journal.jsonl              # task lifecycle journal (git-ignored)
```

- `ProjectRepository.list_projects()` walks `projects/`, validates uuid dir
  names, reads each `project.json`, and returns metadata sorted by
  `updated_at` (falling back to file `mtime` for legacy projects). Corrupt
  entries are logged and skipped.
- `OutputStore.resolve_file` guards path traversal: the resolved target must
  stay inside `output/<project_id>/`.
- The library marks a project **rendered** only when all of
  `infographic.{svg,png,pdf}` exist; otherwise it is a **draft**.

## Project janitor

`ProjectJanitor` (`cleanup.py`) is a background loop started by the app
lifespan:

- Every `CLEANUP_INTERVAL_SECONDS`, `cleanup_once()` deletes
  `projects/<id>` + `output/<id>` for projects whose age (from
  `project.json` `updated_at`, falling back to `mtime`) exceeds
  `PROJECT_RETENTION_SECONDS`.
- Projects referenced by a running task (`TaskManager.active_project_ids()`)
  are skipped.
- `PROJECT_RETENTION_SECONDS=0` disables it.

## ComfyUI workflow contract

`app/workflows/illustration_api.json` is the ComfyUI **API** workflow.
`comfyui_client.py` hardcodes its node IDs:

| Constant | Node ID | Class |
| --- | --- | --- |
| `CHECKPOINT_NODE` | `1` | `CheckpointLoaderSimple` |
| `POSITIVE_PROMPT_NODE` | `3` | `CLIPTextEncode` |
| `NEGATIVE_PROMPT_NODE` | `4` | `CLIPTextEncode` |
| `KSAMPLER_NODE` | `5` | `KSampler` |
| `LATENT_NODE` | `9` | `EmptyLatentImage` |
| `SAVE_IMAGE_NODE` | `13` | `SaveImage` |

`build_workflow` sets the latent to `IMAGE_WIDTH`×`IMAGE_HEIGHT` (1024×1448
portrait) and overrides the checkpoint loader's `ckpt_name` with
`COMFYUI_CHECKPOINT` (so the env var is honored at runtime, not decorative).
**Editing the workflow JSON means re-syncing those constants** — a
pytest contract test (`tests/test_comfyui_contract.py`) asserts every constant
exists in the JSON with the expected type and wiring, and that `build_workflow`
applies the configured checkpoint, so a drift breaks CI instead of failing
silently at runtime.
