import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    FastAPI
)

from fastapi.staticfiles import (
    StaticFiles
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


logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger(
    "infographic"
)


@asynccontextmanager
async def lifespan(
    app: FastAPI
):

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
