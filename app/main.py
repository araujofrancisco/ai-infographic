import base64
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    FastAPI
)

from fastapi.responses import (
    JSONResponse
)

from fastapi.staticfiles import (
    StaticFiles
)

from fastapi.templating import (
    Jinja2Templates
)

from config import (
    settings
)

from cleanup import (
    janitor
)

from routes_ui import (
    router as ui_router
)

from routes_tasks import (
    router as tasks_router
)

from routes_library import (
    router as library_router
)

from tasks import (
    task_manager
)

from workers import (
    close_backends
)


logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger(
    "infographic"
)


def _ensure_data_dirs():

    for name, path in [
        (
            "output",
            Path(
                settings.OUTPUT_DIR
            )
        ),
        (
            "projects",
            Path(
                settings.PROJECTS_DIR
            )
        ),
        (
            "tasks",
            Path(
                settings.TASKS_DIR
            )
        )
    ]:

        path.mkdir(
            parents=True,
            exist_ok=True
        )

        if not (
            path.is_dir()
            and os.access(
                path,
                os.W_OK
            )
        ):

            raise RuntimeError(
                f"data directory {name} at {path} "
                "is not writable"
            )


@asynccontextmanager
async def lifespan(
    app: FastAPI
):

    _ensure_data_dirs()

    restored = task_manager.restore()

    if restored:

        logger.info(
            "restored %d task(s) from journal",
            restored
        )

    await janitor.start()

    yield

    await janitor.stop()

    await close_backends()


app = FastAPI(
    title="AI Infographic Generator",
    lifespan=lifespan
)


def _dirs_ok() -> bool:

    for path in [
        settings.OUTPUT_DIR,
        settings.PROJECTS_DIR,
        settings.TASKS_DIR
    ]:

        candidate = Path(
            path
        )

        if not (
            candidate.is_dir()
            and os.access(
                candidate,
                os.W_OK
            )
        ):

            return False

    return True


@app.get(
    "/healthz"
)
async def healthz():

    ok = _dirs_ok()

    return JSONResponse(
        {
            "ok": ok
        },
        status_code=(
            200
            if ok
            else 503
        )
    )


def _auth_enabled() -> bool:

    return bool(
        settings.AUTH_USER
        and settings.AUTH_PASSWORD
    )


@app.middleware(
    "http"
)
async def basic_auth(
    request,
    call_next
):

    if not _auth_enabled():

        return await call_next(
            request
        )

    if request.url.path.startswith(
        "/healthz"
    ):

        return await call_next(
            request
        )

    auth = (
        request.headers.get(
            "authorization",
            ""
        )
    )

    expected = (
        "Basic "
        + base64.b64encode(
            f"{settings.AUTH_USER}:{settings.AUTH_PASSWORD}".encode(
                "utf-8"
            )
        ).decode(
            "ascii"
        )
    )

    if secrets.compare_digest(
        auth,
        expected
    ):

        return await call_next(
            request
        )

    return JSONResponse(
        {
            "detail": (
                "Authentication required."
            )
        },
        status_code=401,
        headers={
            "WWW-Authenticate": (
                'Basic realm="infographic"'
            )
        }
    )

static_dir = (
    Path(__file__).parent
    / "static"
)

app.mount(
    "/static",
    StaticFiles(
        directory=str(
            static_dir
        )
    ),
    name="static"
)

templates = Jinja2Templates(
    directory=str(
        Path(__file__).parent
        / "templates"
    )
)


def _error_page(
    request,
    title: str,
    message: str,
    status_code: int
):

    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "request": request,
            "title": title,
            "message": message
        },
        status_code=status_code
    )


@app.exception_handler(
    404
)
async def not_found(
    request,
    exc
):

    return _error_page(
        request,
        "Not found",
        "The page you requested does not exist.",
        404
    )


@app.exception_handler(
    500
)
async def server_error(
    request,
    exc
):

    logger.exception(
        "unhandled error on %s",
        request.url.path
    )

    return _error_page(
        request,
        "Server error",
        "Something went wrong. Check the server logs for details.",
        500
    )


app.include_router(
    ui_router
)

app.include_router(
    tasks_router
)

app.include_router(
    library_router
)
