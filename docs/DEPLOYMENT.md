# Deployment Guide

This guide covers running the AI Infographic Generator for real, including the
two main gotchas: the ComfyUI GPU service and the Ollama model/checkpoint
setup. For common failure symptoms, see
[Troubleshooting](TROUBLESHOOTING.md).

## Contents

- [Architecture at a glance](#architecture-at-a-glance)
- [Prerequisites](#prerequisites)
- [First-run setup](#first-run-setup)
- [Starting and verifying](#starting-and-verifying)
- [Configuration](#configuration)
- [Data, volumes, and backups](#data-volumes-and-backups)
- [Restart behavior](#restart-behavior)
- [Production notes](#production-notes)
- [Updating](#updating)

## Architecture at a glance

`docker compose up` starts two containers defined in `docker-compose.yml`:

| Service | Image | Purpose | Port |
| --- | --- | --- | --- |
| `infographic` | built from `app/Dockerfile` | FastAPI app (web UI, queue, rendering) | `${APP_PORT:-8090}` → container `8080` |
| `comfyui` | `yanwk/comfyui-boot:cu128-slim` | SDXL image generation (needs a GPU) | `8188` |

Ollama is **not** part of the compose stack. It runs wherever you run it
(host, another machine, or a container) and is reached via `OLLAMA_URL`.

```
Browser ──> infographic (FastAPI, :8090)
                ├── POST /generate-content ──> Ollama (OLLAMA_URL)
                └── POST /generate-infographic ──> ComfyUI (COMFYUI_URL)
                                                        └─> writes page.png
```

## Prerequisites

1. **Linux** host (this stack uses the NVIDIA container runtime).
2. **Docker Engine** with Compose v2 (`docker compose version`).
3. **NVIDIA driver** that reports a usable device (`nvidia-smi`).
4. **NVIDIA Container Toolkit** — lets Docker expose the GPU. On Debian/Ubuntu:

   ```bash
   sudo apt-get install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```

   If `docker compose up` fails with
   `could not select device driver "nvidia"`, the toolkit is not installed or
   the daemon was not restarted. Verify with:

   ```bash
   docker run --rm --gpus all nvidia/cuda:12.3.1-base-ubuntu22.04 nvidia-smi
   ```

5. **Ollama** installed and running where the app can reach it, with the model
   pulled:

   ```bash
   ollama serve        # usually already running as a service
   ollama pull gemma4:12b
   ```

   Default `OLLAMA_URL` is `http://host.docker.internal:11434`, which works on
   Docker Desktop and when the compose file maps `host.docker.internal` to the
   host gateway (`extra_hosts`). If Ollama runs on a different machine or port,
   set `OLLAMA_URL` accordingly (see
   [Configuration](#configuration)).

6. **Disk space.** The mounted `comfyui/` directory (models, python, etc.) is
   roughly 6.6 GB before you add checkpoints; the SDXL base checkpoint is
   another ~6.9 GB. `output/`, `projects/`, and `tasks/` grow over time (the
   janitor deletes old projects automatically; see
   [Production notes](#production-notes)).

## First-run setup

1. **Create `.env`** at the repo root (git-ignored). Compose reads it; the app
   does not load `.env` itself, it relies on the environment Compose passes.

   ```bash
   cat > .env <<'EOF'
   OLLAMA_URL=http://host.docker.internal:11434
   OLLAMA_MODEL=gemma4:12b

   COMFYUI_URL=http://comfyui:8188

   COMFYUI_CHECKPOINT=sd_xl_base_1.0.safetensors

   APP_PORT=8090
   EOF
   ```

   The compose file also passes through the optional tunables with defaults:
   `OLLAMA_MAX_ATTEMPTS=3`, `COMFYUI_MAX_WAIT_SECONDS=1200`,
   `TASK_TTL_SECONDS=1800`, `TASKS_DIR=/app/tasks`,
   `MAX_QUEUED_PER_KIND=2`, `PROJECT_RETENTION_SECONDS=2592000`,
   `CLEANUP_INTERVAL_SECONDS=3600`.

2. **Install the SDXL checkpoint for ComfyUI.** The workflow defaults to
   `sd_xl_base_1.0.safetensors`, and the compose file mounts
   `./comfyui/models` into `/root/ComfyUI/models`, so place the file at:

   ```
   comfyui/models/checkpoints/sd_xl_base_1.0.safetensors
   ```

   The checkpoint name is applied at render time from the `COMFYUI_CHECKPOINT`
   env var (`app/comfyui_client.py` sets node 1's `ckpt_name`), so the file
   must be present under the configured name in
   `comfyui/models/checkpoints/`. To use a different checkpoint, change
   `COMFYUI_CHECKPOINT` in `.env` and make sure the file exists there — no
   workflow editing needed.

   > The checkpoint can be downloaded from Hugging Face
   > (`stabilityai/stable-diffusion-xl-base-1.0`, file
   > `sd_xl_base_1.0.safetensors`). The exact URL changes; fetch it through the
   > Hugging Face file listing rather than guessing a direct link.

3. **Ensure the Ollama model is pulled** (step 5 of Prerequisites). The app
   fails a content task with a clear message if the model is missing.

## Starting and verifying

```bash
docker compose up --build -d
docker compose ps
```

The first `--build` takes a while (pip installs + ComfyUI image pull). Watch
logs while it warms up:

```bash
docker compose logs -f infographic
docker compose logs -f comfyui
```

ComfyUI is slow to become ready on the first boot (model loading / possible
downloads). The app caps any wait at `COMFYUI_MAX_WAIT_SECONDS` (default
1200 s) and will surface a timeout message if it never completes.

Smoke-test the web app:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8090/   # 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8188/   # 200 (ComfyUI)
```

Then generate a real infographic end to end:

1. Open http://localhost:8090.
2. Enter a topic and click **Generate Content**.
3. On the review page click **Generate infographic** (first run: keep
   **Regenerate the page illustration** checked — there is no `page.png` yet).
4. Download the PDF from the result page.

> The first generation is the slowest: cold Ollama model load and a fresh SDXL
> run. Expect minutes, not seconds.

## Configuration

See the README's [Configuration table](../README.md#configuration) for every
variable. Key deployment-specific ones:

| Variable | Default | Deployment note |
| --- | --- | --- |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Use the host gateway; if Ollama is remote, use its reachable URL. Must be reachable *from inside* the `infographic` container. |
| `COMFYUI_URL` | `http://comfyui:8188` | In compose this is the service DNS name. Outside compose (local dev), use `http://localhost:8188`. |
| `COMFYUI_CHECKPOINT` | `sd_xl_base_1.0.safetensors` | Checkpoint name applied to the ComfyUI workflow at render time. Must match a file in `comfyui/models/checkpoints/`. |
| `APP_PORT` | `8090` | Host port for the web UI. Change to free up a port conflict. |
| `COMFYUI_MAX_WAIT_SECONDS` | `1200` | Raise on slow GPUs; lowers timeouts if ComfyUI is unhealthy. |
| `MAX_QUEUED_PER_KIND` | `2` | One task runs per kind; this is how many may queue. Raise for bursty use. |
| `PROJECT_RETENTION_SECONDS` | `2592000` (30 d) | Set `0` to disable automatic project cleanup. |

## Data, volumes, and backups

Compose bind-mounts three host directories into the `infographic` container:

| Host dir | Container path | Contents |
| --- | --- | --- |
| `./projects` | `/app/projects` | `projects/<uuid>/project.json` — topic, style, content, timestamps |
| `./output` | `/app/output` | `output/<uuid>/infographic.{svg,png,pdf}` — rendered files |
| `./tasks` | `/app/tasks` | `tasks/journal.jsonl` — task lifecycle journal |

Plus the ComfyUI mounts (`./comfyui/{models,input,output,workflows}`).

To back up everything the app produced, stop the app and copy `projects/`,
`output/`, and `tasks/`. These directories are git-ignored by design (runtime
data, and `comfyui/` is huge).

At boot the app verifies the three data directories exist and are writable;
if not, it **exits immediately** with an error naming the offending directory.

## Restart behavior

- Task state is journaled to `tasks/journal.jsonl` on every lifecycle
  transition (created / started / terminal), never on progress ticks.
- On boot the app replays the journal into memory:
  - **Finished** tasks come back, so status pages and the `/activity` feed
    survive restarts.
  - **Pending/running** tasks are marked **failed** with the message
    *"The server restarted while this task was running. Please start it
    again."* — the browser poller gets a terminal state instead of a 404.
- In-memory task state is otherwise single-worker by design; do not scale the
  `infographic` service to multiple replicas expecting shared state.

## Production notes

- **Single app worker.** Long-running work runs inside the same process
  (`asyncio.create_task`). One `infographic` container is the intended
  deployment.
- **Queue limits.** Per kind (`content` / `infographic`) one task runs at a
  time and up to `MAX_QUEUED_PER_KIND` wait. The UI shows a
  "The generation queue is full" message when a slot is not free; it does not
  block.
- **Retention.** The `ProjectJanitor` background loop (every
  `CLEANUP_INTERVAL_SECONDS`) deletes `projects/<id>` + `output/<id>` for
  projects older than `PROJECT_RETENTION_SECONDS`, skipping projects referenced
  by a running task. `PROJECT_RETENTION_SECONDS=0` disables it.
- **Ollama timeout.** The content call has a fixed 600 s client timeout with a
  distinct connect-vs-timeout error message. Cold 12B model loads and
  single-slot queueing mean this can be hit; raise `OLLAMA_MAX_ATTEMPTS` only
  if retries are the bottleneck (timeouts are not retried).
- **GPU headroom.** SDXL at 1024×1448 needs comfortable VRAM. If ComfyUI
  errors with CUDA OOM, check `docker compose logs comfyui` and close other
  GPU consumers (see [Troubleshooting](TROUBLESHOOTING.md)).

## Updating

There are no migrations; data is plain JSON + JSONL files.

```bash
git pull
docker compose build infographic        # pick up app/ changes
docker compose up -d
```

ComfyUI is a pinned image (`yanwk/comfyui-boot:cu128-slim`); pull a newer tag
explicitly if you need it. The checkpoint and your data are untouched by
rebuilds.
