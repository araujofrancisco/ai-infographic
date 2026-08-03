import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    Form,
    Request
)

from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse
)

from fastapi.templating import (
    Jinja2Templates
)

from pydantic import ValidationError

from models import (
    InfographicContent
)

from services import (
    ContentService
)

from storage import (
    OutputStore,
    ProjectNotFound,
    ProjectRepository
)

from tasks import (
    QueueFullError,
    task_manager
)

from workers import (
    content_worker,
    infographic_worker
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

content_service = ContentService()

repo = ProjectRepository()

outputs = OutputStore()

router = APIRouter()


@router.get(
    "/",
    response_class=HTMLResponse
)
async def index(
    request: Request
):

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request
        }
    )


@router.post(
    "/generate-content",
    response_class=HTMLResponse
)
async def generate_content(
    request: Request,
    topic: str = Form(...),
    audience: str = Form("Beginner"),
    style: str = Form("Technical / Modern"),
    section_count: int = Form(6)
):

    form = {
        "topic": topic,
        "audience": audience,
        "style": style,
        "section_count": section_count
    }

    try:

        task_id = task_manager.start(
            kind="content",
            worker=lambda set_progress: (
                content_worker(
                    set_progress,
                    topic=topic,
                    audience=audience,
                    style=style,
                    section_count=section_count
                )
            ),
            form=form
        )

    except QueueFullError:

        logger.warning(
            "content queue full; rejecting request for %r",
            topic
        )

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "request": request,
                "error": (
                    "The generation queue is full. "
                    "Please wait a moment and try again."
                ),
                **form
            }
        )

    logger.info(
        "started content task %s",
        task_id
    )

    return templates.TemplateResponse(
        request=request,
        name="working.html",
        context={
            "request": request,
            "task_id": task_id,
            "page": "review",
            "message": (
                "Generating content with Ollama. "
                "This can take a minute or two…"
            )
        }
    )


@router.post(
    "/save-content"
)
async def save_content(
    request: Request,
    project_id: str = Form(...),
    content_json: str = Form(...)
):

    wants_json = (
        request.query_params.get(
            "json"
        )
        == "1"
    )

    try:

        content = InfographicContent.model_validate_json(
            content_json
        )

    except ValidationError as exc:

        logger.error(
            "save-content validation failed for %s: %s",
            project_id,
            exc
        )

        if wants_json:

            detail = "; ".join(
                error.get(
                    "msg",
                    ""
                )
                for error in exc.errors()
            )

            return JSONResponse(
                {
                    "ok": False,
                    "error": (
                        "Content validation failed: "
                        + (detail or str(exc))
                    )
                },
                status_code=400
            )

        return RedirectResponse(
            url=f"/review/{project_id}?save_error=1",
            status_code=303
        )

    try:

        content_service.save_content(
            project_id,
            content
        )

    except ProjectNotFound:

        if wants_json:

            return JSONResponse(
                {
                    "ok": False,
                    "error": "Project not found."
                },
                status_code=404
            )

        return RedirectResponse(
            url="/",
            status_code=303
        )

    if wants_json:

        return {
            "ok": True
        }

    return RedirectResponse(
        url=f"/review/{project_id}?saved=1",
        status_code=303
    )


@router.get(
    "/review/{project_id}",
    response_class=HTMLResponse
)
async def review(
    request: Request,
    project_id: str
):

    content = repo.load_content(
        project_id
    )

    if content is None:

        return HTMLResponse(
            "Project not found",
            status_code=404
        )

    context = {
        "request": request,
        "project_id": project_id,
        "content": content
    }

    if request.query_params.get(
        "saved"
    ):

        context["notice"] = (
            "Content saved."
        )

    if request.query_params.get(
        "save_error"
    ):

        context["error"] = (
            "The content could not be saved because it did not "
            "match the expected structure. Please fix the fields "
            "and save again."
        )

    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context=context
    )


@router.get(
    "/result/{project_id}",
    response_class=HTMLResponse
)
async def result(
    request: Request,
    project_id: str
):

    if not outputs.all_exist(
        project_id
    ):

        return HTMLResponse(
            "Infographic not found",
            status_code=404
        )

    files = outputs.files(
        project_id
    )

    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "request": request,
            "project_id": project_id,
            "files": {
                name: str(path)
                for name, path in files.items()
            }
        }
    )


@router.post(
    "/generate-infographic",
    response_class=HTMLResponse
)
async def generate_infographic(
    request: Request,
    project_id: str = Form(...),
    force: bool = Form(False)
):

    content = repo.load_content(
        project_id
    )

    if content is None:

        return HTMLResponse(
            "Project not found",
            status_code=404
        )

    form = {
        "project_id": project_id,
        "force": force
    }

    try:

        task_id = task_manager.start(
            kind="infographic",
            worker=lambda set_progress: (
                infographic_worker(
                    set_progress,
                    project_id=project_id,
                    force=force
                )
            ),
            form=form
        )

    except QueueFullError:

        logger.warning(
            "infographic queue full for project %s",
            project_id
        )

        return templates.TemplateResponse(
            request=request,
            name="review.html",
            context={
                "request": request,
                "project_id": project_id,
                "content": content,
                "error": (
                    "The rendering queue is full. "
                    "Please wait a moment and try again."
                )
            }
        )

    logger.info(
        "started infographic task %s (force=%s)",
        task_id,
        force
    )

    return templates.TemplateResponse(
        request=request,
        name="working.html",
        context={
            "request": request,
            "task_id": task_id,
            "page": "result",
            "message": (
                "Rendering the page illustration with ComfyUI. "
                "This can take a couple of minutes…"
            )
        }
    )


@router.get(
    "/files/{project_id}/{filename}"
)
async def get_file(
    project_id: str,
    filename: str
):

    file_path = outputs.resolve_file(
        project_id,
        filename
    )

    if file_path is None:

        return HTMLResponse(
            "File not found",
            status_code=404
        )

    return FileResponse(
        file_path
    )
