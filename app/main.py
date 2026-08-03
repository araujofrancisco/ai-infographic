import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    FastAPI
)

from fastapi.staticfiles import (
    StaticFiles
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

from tasks import (
    task_manager
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


app = FastAPI(
    title="AI Infographic Generator",
    lifespan=lifespan
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

app.include_router(
    ui_router
)

app.include_router(
    tasks_router
)
