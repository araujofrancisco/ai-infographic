from pathlib import Path

from fastapi import (
    APIRouter,
    HTTPException,
    Request
)

from fastapi.responses import (
    HTMLResponse
)

from fastapi.templating import (
    Jinja2Templates
)

from storage import (
    ProjectRepository
)

from tasks import (
    task_manager
)


templates = Jinja2Templates(
    directory=str(
        Path(__file__).parent
        / "templates"
    )
)

repo = ProjectRepository()

router = APIRouter()


def _field_value(
    value
) -> str:

    if isinstance(
        value,
        bool
    ):

        return "1" if value else "0"

    return str(
        value
    )


def _retry_for(
    task
) -> dict | None:

    form = task.form or {}

    if task.kind == "infographic":

        fields = [
            {
                "name": name,
                "value": _field_value(
                    form[name]
                )
            }
            for name in [
                "project_id",
                "force"
            ]
            if name in form
        ]

        if not fields:

            return None

        return {
            "action": "/generate-infographic",
            "button": (
                "Try generating the infographic again"
            ),
            "fields": fields
        }

    fields = [
        {
            "name": name,
            "value": _field_value(
                form[name]
            )
        }
        for name in [
            "topic",
            "audience",
            "style",
            "section_count"
        ]
        if name in form
    ]

    if not fields:

        return None

    return {
        "action": "/generate-content",
        "button": "Try generating content again",
        "fields": fields
    }


@router.get(
    "/tasks/{task_id}/status"
)
async def task_status(
    task_id: str
):

    task = task_manager.get(
        task_id
    )

    if task is None:

        raise HTTPException(
            status_code=404,
            detail="Task not found"
        )

    return task_manager.to_dict(
        task
    )


@router.get(
    "/tasks/{task_id}",
    response_class=HTMLResponse
)
async def task_page(
    request: Request,
    task_id: str
):

    task = task_manager.get(
        task_id
    )

    if task is None:

        return HTMLResponse(
            "Task not found",
            status_code=404
        )

    error = task.error

    if task.status == "cancelled":

        error = error or (
            "This task was cancelled."
        )

    if task.kind == "infographic":

        project_id = (
            task.project_id
            or task.form.get(
                "project_id"
            )
        )

        content = repo.load_content(
            project_id
        )

        if content is None:

            return HTMLResponse(
                "Project not found",
                status_code=404
            )

        return templates.TemplateResponse(
            request=request,
            name="review.html",
            context={
                "request": request,
                "project_id": project_id,
                "content": content,
                "error": error,
                "retry": _retry_for(
                    task
                )
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "error": error,
            "retry": _retry_for(
                task
            ),
            "topic": task.form.get(
                "topic",
                ""
            ),
            "audience": task.form.get(
                "audience",
                "Beginner"
            ),
            "style": task.form.get(
                "style",
                "Technical / Modern"
            ),
            "section_count": task.form.get(
                "section_count",
                6
            )
        }
    )
