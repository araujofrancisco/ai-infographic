# Troubleshooting

Diagnose by symptom. Each section is a table of **Symptom → Cause → Fix**.
Start with [Checking container health](#checking-container-health), then jump
to the relevant area. Most "generate content / infographic" failures are
surfaced as a red banner in the web UI with a specific message; search that
message here.

## Checking container health

```bash
docker compose ps                              # is comfyui / infographic running?
docker compose logs --tail=200 infographic     # app errors, task lifecycle
docker compose logs --tail=200 comfyui         # SDXL errors, OOM, model load
nvidia-smi                                     # GPU present? VRAM free?
curl -s http://localhost:8090/ -o /dev/null -w "%{http_code}\n"
curl -s http://localhost:8188/ -o /dev/null -w "%{http_code}\n"
```

## Docker / GPU

| Symptom | Cause | Fix |
| --- | --- | --- |
| `docker compose up` fails: `could not select device driver "nvidia"` | NVIDIA Container Toolkit not installed, or daemon not restarted after install | `sudo apt-get install -y nvidia-container-toolkit && sudo systemctl restart docker`; verify with `docker run --rm --gpus all nvidia/cuda:12.3.1-base-ubuntu22.04 nvidia-smi` |
| `comfyui` container exits/restarts immediately | No usable GPU exposed, or image failed to init | Check `docker compose logs comfyui`; confirm `nvidia-smi` works on the host; ensure the driver supports the toolkit version |
| `nvidia-smi` errors / no devices | Host driver missing or wrong for the GPU | Install/match the NVIDIA driver for your GPU and reboot |
| Generation is extremely slow or the ComfyUI wait always times out | Cold model load, slow GPU, or VRAM pressure sharing with other processes | This is expected on first runs; raise `COMFYUI_MAX_WAIT_SECONDS`; stop other GPU workloads |
| Docker pull of `yanwk/comfyui-boot:cu128-slim` fails / huge download | Network or registry limits | Retry; the image is multi-GB. Ensure disk space is available |

## Ollama (content generation)

The web UI error for these begins with *"Ollama is not reachable at ..."*,
*"Ollama took longer than 10 minutes ..."*, *"Ollama request failed"*,
or *"Ollama returned invalid JSON ..."*.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Ollama is not reachable at http://host.docker.internal:11434` | Ollama not running, wrong host/port, or not reachable from inside the container | Confirm `ollama list` works on the host; set `OLLAMA_URL` to a URL reachable *from the container*; on Linux check that compose maps `host.docker.internal` (`extra_hosts` already does) or use the host LAN IP |
| `Ollama took longer than 10 minutes` | Cold load of a large model or a busy single-slot Ollama; the client timeout is fixed at 600 s | Wait for the model to warm, then retry; keep other Ollama requests off the same server |
| Model error like `model "gemma4:12b" not found` | `OLLAMA_MODEL` not pulled | `ollama pull gemma4:12b` (or your configured model) |
| `Ollama returned invalid JSON` / `content does not match the expected schema` repeatedly | Model output doesn't satisfy the Pydantic schema after all `OLLAMA_MAX_ATTEMPTS` corrective retries | Retry (transient); the retry loop usually fixes it; consider a different/quantized model; verify Ollama's `format`/structured output support for your model |
| Content task spins for a long time then fails | Big model cold start + corrective retries | Expected on first use; increase patience before treating as a bug |
| Content generated but sections/bullets look wrong (too long, etc.) | Prompt drift on the model | Edit on the review page — it is fully editable and persists |

## ComfyUI (illustration rendering)

Errors typically show as *"Cannot reach ComfyUI at ..."*, *"ComfyUI rejected the
workflow"*, *"ComfyUI workflow failed: ..."*, or *"ComfyUI did not finish the
workflow within ... seconds"*.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Cannot reach ComfyUI at http://comfyui:8188` | ComfyUI container not up yet, crashed, or `COMFYUI_URL` wrong | `docker compose ps` + logs; in local dev set `COMFYUI_URL=http://localhost:8188` |
| `ComfyUI rejected the workflow (400): ...` | Workflow invalid, or a node/model reference missing | Check that the checkpoint named by `COMFYUI_CHECKPOINT` (applied at render time to `workflows/illustration_api.json` node 1) matches a file in `comfyui/models/checkpoints/` |
| Node error about `ckpt_name` / `model not found` | SDXL base checkpoint not installed | Place the file named by `COMFYUI_CHECKPOINT` (default `sd_xl_base_1.0.safetensors`) in `comfyui/models/checkpoints/` (see [Deployment](DEPLOYMENT.md#first-run-setup)); restart ComfyUI so it rescans models |
| `ComfyUI did not finish the workflow within 1200 seconds` | Slow GPU, queue backlog, or hung prompt | Check `docker compose logs comfyui`; raise `COMFYUI_MAX_WAIT_SECONDS`; reduce load |
| CUDA out-of-memory error in ComfyUI logs | SDXL 1024×1448 exceeds free VRAM | Close other GPU consumers, lower image load, add VRAM; see logs for the exact allocation failure |
| `ComfyUI completed the workflow but no output image was found` | Workflow finished without a save step / wrong output node | Verify `app/workflows/illustration_api.json` still has `SaveImage` (node 13) and matches `app/comfyui_client.py` constants (see [Architecture](ARCHITECTURE.md#comfyui-workflow-contract)) |
| Illustration has text/letters baked in | The image model ignored the negative prompt | Regenerate (the prompt aggressively forbids text); occasionally repeat until clean |

## App startup / configuration

| Symptom | Cause | Fix |
| --- | --- | --- |
| App container exits immediately with `data directory ... is not writable` | `output/`, `projects/`, or `tasks/` missing or read-only at boot | Create them writable on the host (compose mounts them); check ownership/permissions; this fail-fast is intentional |
| Port conflict (`Address already in use`) | Another process owns `APP_PORT` or `8188` | Change `APP_PORT` in `.env`; for ComfyUI remap the port in `docker-compose.yml` |
| `static/` CSS/JS 404s | App mounted but files missing in image | Rebuild (`docker compose build infographic`); the Dockerfile copies `app/` including `static/` |
| Browser shows 500 when opening a task page | Worker died before `project_id` was set (older task) | The page falls back to the task's stored `form["project_id"]`; if still failing, check logs — fixed tasks should render the error banner |
| UI says a page is not found (`Infographic not found`) | `output/<id>/infographic.*` does not exist yet | Generate the infographic first; drafts only exist in `projects/` |

## Tasks, queue, and restart

| Symptom | Cause | Fix |
| --- | --- | --- |
| *"The generation queue is full."* | All slots for that kind busy (1 running + `MAX_QUEUED_PER_KIND` queued) | Wait and retry; raise `MAX_QUEUED_PER_KIND` in `.env` for bursty use |
| Task shows *"The server restarted while this task was running. Please start it again."* | App restarted mid-task; journal replays it as failed | Rerun the generation — this is expected behavior, not data loss |
| Working page says *"This task is no longer available ... server restarted"* | `GET /tasks/{id}/status` 404 after restart | Start the task again; the poller stops cleanly instead of spinning |
| Task stuck on "Running" forever | ComfyUI hung past the wait cap or worker crashed silently | Check logs; the task fails at `COMFYUI_MAX_WAIT_SECONDS`; regenerate |
| Delete button returns `This project is currently being generated` (409) | The project is referenced by an active task | Wait for the task to finish, then delete |
| Duplicate/corrupt entries in the activity feed | Journal file corruption | The store skips unparseable lines with a warning; the journal is append-only and safe to trim manually if needed |

## Rendering / output quality

| Symptom | Cause | Fix |
| --- | --- | --- |
| Result page 404s right after a successful render | Files written but `all_exist` check races the redirect | Reload; if persistent, rerun the infographic task |
| Text overflows the page / fonts tiny | Content is long; the renderer auto-shrinks fonts to `MIN_SCALE=0.6` | Trim bullets/descriptions on the review page and regenerate |
| Text unreadable over the art | The illustration is busy where text sits | Regenerate the illustration; the left 45% should stay calm per the prompt; the app also blurs the left text column |
| PDF renders but PNG looks different | `cairosvg` renders SVG→PDF vs SVG→PNG separately | Expected; both derive from the same `build_svg()` output |
| Downloaded files are empty | Old partial output from an interrupted render | Regenerate with **Regenerate the page illustration** to rebuild `output/<id>/` |
| `page.png` reused from a previous render when you wanted a new one | Resume behavior (existing non-empty `page.png` is kept) | Check **Regenerate the page illustration** (`force=1`) before generating |

## Local development (no Docker)

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ImportError: libcairo...` / `cairosvg` import fails | Missing system libraries | Install `libcairo2`, `libpango-1.0-0`, `libpangocairo-1.0-0`, `libgdk-pixbuf-2.0-0` (and fonts) — the Docker image installs these; bare venvs need them too |
| Ollama/ComfyUI not found in local dev | Defaults point at container hostnames | Set `OLLAMA_URL=http://localhost:11434` and `COMFYUI_URL=http://localhost:8188` |
| Generation is very slow locally | No GPU in ComfyUI / model loading per process | This is expected; use the Docker GPU stack for real rendering |

## Maintenance

| Symptom | Cause | Fix |
| --- | --- | --- |
| Disk filling up | `output/` + `comfyui/` grow | Verify the janitor ran (`CLEANUP_INTERVAL_SECONDS`); lower `PROJECT_RETENTION_SECONDS`; set `0` to disable cleanup; prune `comfyui/output`/logs |
| Journal grows unbounded | It records every transition, never progress ticks | It is intentionally small (a handful of lines per task); if it becomes large, rotate it while the app is stopped |
| GitHub Actions doesn't run | CI was dormant until a remote existed | The repo now has a remote (`araujofrancisco/ai-infographic`); CI runs on `push`/`pull_request` — check Actions on GitHub |
