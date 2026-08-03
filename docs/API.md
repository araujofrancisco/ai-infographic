# API Reference

The app is primarily an HTML UI, so almost every endpoint returns a rendered
page. The machine-readable endpoints are the **task status** endpoint (polled
by `working.html`), **save-content in JSON mode** (polled by the review page),
and **delete** (called by the library). All routes are served by the FastAPI
app (`app.main:app`).

Base URL: `http://<host>:<APP_PORT>/` (default port `8090`).

## Contents

- [Routes overview](#routes-overview)
- [UI routes](#ui-routes)
- [Library routes](#library-routes)
- [Task routes](#task-routes)
- [Static assets](#static-assets)
- [Schemas](#schemas)
- [Task status payload](#task-status-payload)
- [Error semantics](#error-semantics)

## Routes overview

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | New-infographic form (index page) |
| POST | `/generate-content` | Start a content-generation task |
| POST | `/save-content` | Save edited content (HTML or JSON mode) |
| GET | `/review/{project_id}` | Editable review page for a draft |
| GET | `/result/{project_id}` | Result/download page (only when rendered) |
| POST | `/generate-infographic` | Start a rendering task |
| GET | `/files/{project_id}/{filename}` | Serve a rendered output file |
| GET | `/projects` | Project library (thumbnail grid) |
| GET | `/projects/{project_id}/thumbnail` | Preview image for a card |
| POST | `/projects/{project_id}/delete` | Hard-delete a project |
| GET | `/activity` | Task history feed |
| GET | `/tasks/{task_id}/status` | JSON task status (poller) |
| GET | `/tasks/{task_id}` | Task error page |
| GET | `/static/*` | CSS/JS assets |

## UI routes

### `GET /`

Renders `index.html` — the topic/audience/style/sections form.

**Response:** `200` HTML.

### `POST /generate-content`

Starts a `content` task and returns the working page immediately; the page
polls `/tasks/{id}/status`.

**Form fields:**

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `topic` | yes | — | The subject of the infographic |
| `audience` | no | `Beginner` | One of `Beginner`, `Intermediate`, `Advanced`, `Technical Professional` |
| `style` | no | `Technical / Modern` | One of `Technical / Modern`, `Minimal`, `Isometric`, `Educational`, `Hand Drawn` |
| `section_count` | no | `6` | One of `4`, `6`, `8` |

**Responses:**

- `200` `working.html` with `task_id` and `page="review"`.
- `200` `index.html` with an error banner if the queue is full
  (`"The generation queue is full. Please wait a moment and try again."`).
  (Returned as a page, not an HTTP error code.)

### `POST /save-content`

Persists edited content. Two modes:

- **HTML mode (default):** redirects to `/review/{id}` with a query flag.
- **JSON mode:** pass `?json=1`; returns JSON. Used by `static/review.js`.

**Form fields:**

| Field | Required | Notes |
| --- | --- | --- |
| `project_id` | yes | UUID of the project |
| `content_json` | yes | JSON string matching `InfographicContent` |

**Responses (JSON mode):**

- `200` `{"ok": true}`
- `400` `{"ok": false, "error": "Content validation failed: <detail>"}`
- `404` `{"ok": false, "error": "Project not found."}`

**Responses (HTML mode):**

- `303` → `/review/{project_id}?saved=1` on success.
- `303` → `/review/{project_id}?save_error=1` on validation failure.
- `303` → `/` on missing project.

### `GET /review/{project_id}`

Renders the editable review page for a draft project.

**Responses:**

- `200` HTML with fields bound to `InfographicContent`.
- `404` plain text `"Project not found"` if the project or its content is
  missing/corrupt.

### `GET /result/{project_id}`

Renders the result/download page. **Only** served when all output files
(`infographic.{svg,png,pdf}`) exist.

**Responses:**

- `200` HTML.
- `404` plain text `"Infographic not found"` otherwise.

### `POST /generate-infographic`

Starts an `infographic` task and returns the working page.

**Form fields:**

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `project_id` | yes | — | UUID of the project |
| `force` | no | `false` | `1` regenerates `page.png`; `0` reuses an existing illustration |

**Responses:**

- `200` `working.html` with `task_id` and `page="result"`.
- `200` `review.html` with an error banner if the queue is full.
- `404` plain text `"Project not found"` if the project has no content.

### `GET /files/{project_id}/{filename}`

Serves a file from `output/<project_id>/`. The filename is resolved inside the
project's output directory and path traversal is rejected.

**Responses:**

- `200` the file (`FileResponse`).
- `404` plain text `"File not found"` if missing or outside the directory.

## Library routes

### `GET /projects`

Renders `library.html` — a thumbnail grid of every project. Each card carries
`has_output` (rendered = svg+png+pdf all exist) and links to the review or
result page, a PDF download link when rendered, and a delete button.

**Query parameters:**

| Param | Default | Notes |
| --- | --- | --- |
| `q` | empty | Case-insensitive substring filter on topic/audience/style. |
| `page` | `1` | 1-based page, paginated at `PAGE_SIZE` (default 12). Out-of-range pages clamp to the last page. |

The page shows a search box, a pager when more than one page matches, and a
distinct "no matches" empty state (with a clear-search link) when `q` filters
everything out.

**Response:** `200` HTML.

### `GET /projects/{project_id}/thumbnail`

Serves a preview image: the rendered `output/<id>/infographic.png` if present,
otherwise the raw `projects/<id>/page.png` illustration.

**Responses:**

- `200` PNG (`FileResponse`).
- `404` JSON `{"detail": "Project not found"}` if the id is not a UUID.
- `404` JSON `{"detail": "No preview available"}` if no image exists.

### `POST /projects/{project_id}/delete`

Hard-deletes `projects/<id>` and `output/<id>`.

**Responses:**

- `200` `{"ok": true}`
- `404` `{"ok": false, "error": "Project not found."}` (also returned when the
  id is not a valid UUID)
- `409` `{"ok": false, "error": "This project is currently being generated. Try again in a moment."}`
  when a running task references the project.

### `GET /activity`

Renders `activity.html` — the tail of the task journal (last ~30 events) with
status, duration, and links back to projects.

**Response:** `200` HTML.

## Task routes

### `GET /tasks/{task_id}/status`

The JSON status endpoint polled by `working.html`. Never returns progress
ticks from the journal — it reflects live in-memory task state.

**Responses:**

- `200` [Task status payload](#task-status-payload).
- `404` JSON `{"detail": "Task not found"}`.

### `GET /tasks/{task_id}`

Renders the task error page: `index.html` (content tasks) or `review.html`
(infographic tasks) with an error banner, echoing the form values stored on
the task. A one-click **Try again** form is rendered when the stored form has
enough data to re-submit: it posts to `/generate-content` (content tasks) or
`/generate-infographic` (infographic tasks) with the original hidden fields,
reusing the exact inputs from the failed run.

**Responses:**

- `200` HTML.
- `404` plain text `"Task not found"`.
- `404` plain text `"Project not found"` if an infographic task references a
  missing project.

## Static assets

`GET /static/*` serves `app/static/`: `style.css`, `app.js` (index/result
form spinner), `review.js` (review save/generate), `library.js` (delete flow).

## Schemas

`app/models.py` (Pydantic v2). These are the content structures validated
against `content_json` and produced by Ollama.

```json
{
  "title": "Docker Networking",
  "subtitle": "A quick reference for beginners",
  "sections": [
    {
      "title": "Networks",
      "short_description": "How containers talk to each other.",
      "bullet_points": [
        "Bridge: default driver",
        "Host: shares the host stack"
      ],
      "visual_description": "An abstract illustration of connected nodes."
    }
  ]
}
```

| Model | Fields | Constraints |
| --- | --- | --- |
| `InfographicContent` | `title`, `subtitle`, `sections` | `sections` length 3–8 |
| `Section` | `title`, `short_description`, `bullet_points`, `visual_description` | `bullet_points` length 2–5 |

> The route layer uses **form fields**, not JSON bodies. `GenerateRequest`
> and `GenerateInfographicRequest` in `models.py` are defined for reference
> and validation reuse but are not bound to the HTTP handlers.

## Task status payload

`GET /tasks/{id}/status` returns:

```json
{
  "id": "3f2a...",
  "kind": "content",
  "status": "running",
  "result": {},
  "error": null,
  "project_id": null,
  "progress": {
    "current": 0,
    "total": 1,
    "message": "Generating content with Ollama…"
  },
  "created_at": 1234.5,
  "started_at": 1234.6,
  "finished_at": null
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `status` | string | `pending`, `running`, `succeeded`, `failed`, `cancelled` |
| `result` | object | `{"project_id": "..."}` on success |
| `error` | string \| null | User-facing failure message (e.g. "Project not found.") |
| `progress` | object | `{current, total, message}` as reported by the worker |
| `*_at` | float \| null | `time.monotonic()` based timestamps |

The poller (`working.html`) redirects to `/review/{id}` / `/result/{id}` on
`succeeded`, to `/tasks/{id}` on `failed`/`cancelled`, and shows an actionable
message if the status endpoint 404s (server restart).

## Error semantics

| Endpoint | Code | Meaning |
| --- | --- | --- |
| `/save-content?json=1` | `400` | Content failed validation (details in `error`). |
| `/save-content?json=1` | `404` | Project not found. |
| `/projects/{id}/delete` | `404` | Invalid or missing project. |
| `/projects/{id}/delete` | `409` | Project referenced by a running task. |
| `/tasks/{id}/status` | `404` | Unknown task (e.g. lost on restart). |
| `/review`, `/result`, `/files` | `404` | Missing project, output, or file. |

Task failures (Ollama/ComfyUI errors) do **not** surface as HTTP errors on the
start endpoints; they are recorded on the task (`status: failed`, `error`)
and shown on `/tasks/{id}`.
