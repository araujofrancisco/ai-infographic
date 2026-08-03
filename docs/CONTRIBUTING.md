# Contributing

How to set up a development environment, keep code consistent, and run the
verification gate.

## Contents

- [Local development](#local-development)
- [Code style](#code-style)
- [Testing](#testing)
- [CI](#ci)
- [Conventions and gotchas](#conventions-and-gotchas)

## Local development

The app is a single FastAPI process plus two external services. You can run
just the app against a local Ollama and ComfyUI.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r app/requirements.txt

# Point at your running services
export OLLAMA_URL=http://localhost:11434
export COMFYUI_URL=http://localhost:8188
export PROJECTS_DIR="$PWD/projects"
export OUTPUT_DIR="$PWD/output"
export TASKS_DIR="$PWD/tasks"

uvicorn main:app --port 8080 --app-dir app
```

Open http://localhost:8080. Generation is slow locally: Ollama has a 600 s
timeout and ComfyUI is capped at `COMFYUI_MAX_WAIT_SECONDS`, so expect minutes
and keep Ollama/ComfyUI idle otherwise.

> cairosvg needs system libraries. On the Docker image they are installed via
> `app/Dockerfile`; on a bare host you need `libcairo2`, `libpango-1.0-0`,
> `libpangocairo-1.0-0`, `libgdk-pixbuf-2.0-0`, and fonts
> (`fonts-dejavu`, `fonts-liberation`). See
> [Troubleshooting](TROUBLESHOOTING.md#local-development-no-docker).

## Code style

Match the existing style — consistency matters more than personal preference.

- **One argument per line** for multi-line calls. This is deliberate and is
  *not* auto-formatted (ruff runs only safety rules).
- **Pydantic v2**: use `model_validate` / `model_dump`, not the deprecated v1
  API.
- **No docstrings** on new functions/classes.
- Import `cairosvg` **lazily** inside `render_infographic`, not at module top,
  so `build_svg()` can be tested without libcairo.
- Prefer small modules with clear single responsibilities (see
  [Architecture](ARCHITECTURE.md#component-map)); keep business logic in
  `services.py`, HTTP in the `routes_*` modules, storage in `storage.py`.

## Testing

The gate is `scripts/verify.sh` — three stages, in order:

```bash
scripts/verify.sh
```

1. **`pytest`** — unit + component suite in `tests/`. Configured by
   `pyproject.toml` (`pythonpath = ["app"]`, `testpaths = ["tests"]`).
   Coverage includes: storage timestamps + `list_projects()` ordering and
   corrupt/uuid filtering; the task journal lifecycle and
   `TaskManager.restore()` (terminal replay + interrupted-as-failed);
   renderer wrap/fit boundaries + header wrap/empty-image guard;
   `services.py` (page-prompt motifs, `create_content`, `generate`
   resume-vs-force); UI/task routes via `TestClient` (queue-full,
   `save-content` JSON 400/404, error-page retry forms);
   library/delete/thumbnail/activity/search/pagination routes; and a
   **ComfyUI workflow contract test** asserting every node-ID constant in
   `comfyui_client.py` exists in `workflows/illustration_api.json` with the
   expected type and wiring, plus that `build_workflow` applies
   `COMFYUI_CHECKPOINT`.
2. **`ruff`** — safety rules only: pyflakes `F` + syntax `E9`
   (`pyproject.toml`). Other lints are intentionally off; don't auto-format.
3. **`smoke_test.py`** — a dependency-light check that needs no venv:
   AST-parses every module, asserts `ComfyUIClient` methods are inside the
   class, exercises `renderer.build_svg()` with duck-typed content (stubbing
   pydantic if missing), runs `TaskManager` with fake workers (success/failure/
   progress, queue cap, hard + cooperative cancel, TTL prune, serialization),
   checks `_fit_scale`, and exercises `ProjectJanitor.cleanup_once` (stale vs
   fresh vs active vs disabled).

Run the **full** smoke (imports the whole app, renders a real SVG/PNG/PDF,
builds the ComfyUI workflow, drives the async queue via a live uvicorn
subprocess on port 8092) inside the real image:

```bash
docker build -t infographic-smoke ./app
docker run --rm -v "$(pwd)/smoke_test.py:/smoke_test.py:ro" \
  -w /app infographic-smoke python /smoke_test.py --full
```

> Do **not** use `starlette.testclient.TestClient` for the async flow: it does
> not pump `asyncio.create_task` background tasks created inside handlers.

### Adding a test

- Follow the existing files (`tests/test_storage.py`, `tests/test_tasks.py`,
  etc.) and `tests/helpers.py` (content builders, project writers, `iso_now`).
- `tests/conftest.py` sets temp `PROJECTS_DIR`/`OUTPUT_DIR`/`TASKS_DIR` so unit
  tests never touch real data.
- Add fixtures/data via helpers rather than copying payloads inline.

## CI

`.github/workflows/ci.yml` runs on `push` and `pull_request` and mirrors
`scripts/verify.sh`:

```yaml
steps:
  - actions/checkout@v4
  - actions/setup-python@v5 (3.12)
  - pip install -r app/requirements.txt pytest ruff
  - python -m pytest
  - ruff check
  - python smoke_test.py
```

It is dependency-light (no GPU, no Docker), so it exercises the pure logic and
contracts, not a full end-to-end render.

## Conventions and gotchas

- **Runtime data is git-ignored** by design: `output/`, `projects/`,
  `tasks/`, `comfyui/`, and `.env`. Never commit them.
- **ComfyUI workflow contract.** `app/workflows/illustration_api.json` and the
  node-ID constants in `app/comfyui_client.py` must stay in sync. Editing the
  workflow means re-syncing `CHECKPOINT_NODE` etc. The contract test guards
  this.
- **Image prompts must forbid text.** Illustrations sit inside a text
  infographic; keep "text/letters/words/..." in the negative prompt and never
  ask the image model to render text or labels.
- **Single-worker assumption.** Task state is in-memory (journaled for
  restart recovery, but not shared across processes). Keep the app
  single-worker; do not scale replicas expecting shared queues.
- **Don't await long work in routes.** Start tasks via `TaskManager.start`
  and return the working page immediately; long CPU work (cairosvg) goes
  through `asyncio.to_thread`.
- **Keep the left column calm.** The renderer blurs the left text zone of
  `page.png`; prompts should keep the left ~45% empty for overlaid text.
- Logs use a single `"infographic"` logger; match that for visibility.
