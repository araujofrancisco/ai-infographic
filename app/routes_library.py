import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    APIRouter,
    HTTPException,
    Request
)

from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse
)

from fastapi.templating import (
    Jinja2Templates
)

from storage import (
    OutputStore,
    ProjectRepository
)

from tasks import (
    task_manager
)


logger = logging.getLogger(
    "infographic"
)

templates = Jinja2Templates(
    directory=str(
        Path(__file__).parent
        / "templates"
    )
)

repo = ProjectRepository()

outputs = OutputStore()

router = APIRouter()

STATUS_LABELS = {
    "pending": "Queued",
    "running": "Running",
    "succeeded": "Done",
    "failed": "Failed",
    "cancelled": "Cancelled"
}

TERMINAL_STATUSES = (
    "succeeded",
    "failed",
    "cancelled"
)

PAGE_SIZE = 12


def _is_uuid(
    value: str
) -> bool:

    try:

        parsed = uuid.UUID(
            value
        )

    except ValueError:

        return False

    return str(
        parsed
    ) == value


def _friendly_time(
    iso: str | None
) -> str:

    if not iso:

        return ""

    try:

        parsed = datetime.fromisoformat(
            iso
        )

    except ValueError:

        return iso

    return parsed.astimezone().strftime(
        "%b %d, %Y %H:%M"
    )


def _friendly_duration(
    seconds: int | None
) -> str:

    if seconds is None:

        return ""

    if seconds < 60:

        return f"{seconds}s"

    return (
        f"{seconds // 60}m "
        f"{seconds % 60}s"
    )


def _project_cards(
    q: str = ""
) -> list[dict]:

    cards = []

    for project in repo.list_projects():

        has_output = outputs.all_exist(
            project["id"]
        )

        page_png = (
            repo.project_dir(
                project["id"]
            )
            / "page.png"
        )

        cards.append(
            {
                **project,
                "has_output": has_output,
                "has_thumbnail": (
                    has_output
                    or page_png.exists()
                ),
                "updated": _friendly_time(
                    project["updated_at"]
                ),
                "created": _friendly_time(
                    project["created_at"]
                )
            }
        )

    needle = (
        q.strip().lower()
        if q
        else ""
    )

    if not needle:

        return cards

    return [
        card
        for card in cards
        if (
            needle in (
                card.get(
                    "topic",
                    ""
                )
                or ""
            ).lower()
            or needle in (
                card.get(
                    "audience",
                    ""
                )
                or ""
            ).lower()
            or needle in (
                card.get(
                    "style",
                    ""
                )
                or ""
            ).lower()
        )
    ]


def _activity_feed(
    limit: int = 30
) -> list[dict]:

    by_id: dict[str, dict] = {}

    for snapshot in task_manager.store.read():

        task_id = snapshot.get(
            "id"
        )

        if not task_id:

            continue

        entry = by_id.setdefault(
            task_id,
            {
                "started_ts": None,
                "finished_ts": None
            }
        )

        ts = snapshot.get(
            "ts"
        )

        status = snapshot.get(
            "status"
        )

        if (
            status == "running"
            and ts
        ) and (
            entry["started_ts"] is None
            or ts < entry["started_ts"]
        ):

            entry["started_ts"] = ts

        if (
            status in TERMINAL_STATUSES
            and ts
        ) and (
            entry["finished_ts"] is None
            or ts > entry["finished_ts"]
        ):

            entry["finished_ts"] = ts

        entry.update(
            snapshot
        )

    events = []

    for task_id, entry in by_id.items():

        duration = None

        if (
            entry["started_ts"]
            and entry["finished_ts"]
        ):

            try:

                start = datetime.fromisoformat(
                    entry["started_ts"]
                )

                end = datetime.fromisoformat(
                    entry["finished_ts"]
                )

                duration = int(
                    (end - start).total_seconds()
                )

            except ValueError:

                duration = None

        when = (
            entry["finished_ts"]
            or entry["started_ts"]
            or entry.get(
                "ts"
            )
        )

        form = entry.get(
            "form",
            {}
        ) or {}

        topic = (
            form.get(
                "topic",
                ""
            )
            or "Infographic"
        )

        events.append(
            {
                "id": task_id,
                "kind": entry.get(
                    "kind",
                    ""
                ),
                "status": entry.get(
                    "status",
                    ""
                ),
                "status_label": STATUS_LABELS.get(
                    entry.get(
                        "status"
                    ),
                    entry.get(
                        "status",
                        ""
                    )
                ),
                "error": entry.get(
                    "error"
                ),
                "project_id": entry.get(
                    "project_id"
                ) or form.get(
                    "project_id"
                ),
                "topic": topic,
                "duration": _friendly_duration(
                    duration
                ),
                "when": _friendly_time(
                    when
                )
            }
        )

    events.sort(
        key=lambda item: (
            item["when"]
        ),
        reverse=True
    )

    return events[:limit]


@router.get(
    "/projects",
    response_class=HTMLResponse
)
async def library(
    request: Request,
    q: str = "",
    page: int = 1
):

    cards = _project_cards(
        q
    )

    total = len(
        cards
    )

    total_pages = max(
        1,
        -(
            -total // PAGE_SIZE
        )
    )

    page = min(
        max(
            page,
            1
        ),
        total_pages
    )

    start = (
        (page - 1)
        * PAGE_SIZE
    )

    shown = cards[
        start:
        start + PAGE_SIZE
    ]

    q_encoded = quote(
        q
    )

    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={
            "request": request,
            "active": "library",
            "projects": shown,
            "q": q,
            "q_encoded": q_encoded,
            "page": page,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages
        }
    )


@router.get(
    "/projects/{project_id}/thumbnail"
)
async def project_thumbnail(
    project_id: str
):

    if not _is_uuid(
        project_id
    ):

        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    rendered = (
        outputs.file_path(
            project_id,
            "png"
        )
    )

    if rendered.exists():

        return FileResponse(
            rendered
        )

    page_png = (
        repo.project_dir(
            project_id
        )
        / "page.png"
    )

    if page_png.exists():

        return FileResponse(
            page_png
        )

    raise HTTPException(
        status_code=404,
        detail="No preview available"
    )


@router.post(
    "/projects/{project_id}/delete"
)
async def delete_project(
    project_id: str
):

    if not _is_uuid(
        project_id
    ):

        return JSONResponse(
            {
                "ok": False,
                "error": "Project not found."
            },
            status_code=404
        )

    if project_id in (
        task_manager.active_project_ids()
    ):

        return JSONResponse(
            {
                "ok": False,
                "error": (
                    "This project is currently being "
                    "generated. Try again in a moment."
                )
            },
            status_code=409
        )

    removed = False

    if repo.exists(
        project_id
    ):

        shutil.rmtree(
            repo.project_dir(
                project_id
            ),
            ignore_errors=True
        )

        removed = True

    output_dir = (
        outputs.output_dir(
            project_id
        )
    )

    if output_dir.exists():

        shutil.rmtree(
            output_dir,
            ignore_errors=True
        )

        removed = True

    if not removed:

        return JSONResponse(
            {
                "ok": False,
                "error": "Project not found."
            },
            status_code=404
        )

    logger.info(
        "deleted project %s from library",
        project_id
    )

    return {
        "ok": True
    }


@router.get(
    "/activity",
    response_class=HTMLResponse
)
async def activity(
    request: Request
):

    return templates.TemplateResponse(
        request=request,
        name="activity.html",
        context={
            "request": request,
            "active": "activity",
            "events": _activity_feed()
        }
    )
