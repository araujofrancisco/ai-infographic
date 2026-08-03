import asyncio
import logging
import shutil
import time
from pathlib import Path

from config import settings
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


def _default_active_projects() -> set[str]:

    return task_manager.active_project_ids()


class ProjectJanitor:

    def __init__(
        self,
        repo: ProjectRepository | None = None,
        outputs: OutputStore | None = None,
        max_age: int | None = None,
        interval: int | None = None,
        active_projects=None
    ):

        self.repo = (
            repo
            if repo is not None
            else ProjectRepository()
        )

        self.outputs = (
            outputs
            if outputs is not None
            else OutputStore()
        )

        self.max_age = (
            max_age
            if max_age is not None
            else settings.PROJECT_RETENTION_SECONDS
        )

        self.interval = (
            interval
            if interval is not None
            else settings.CLEANUP_INTERVAL_SECONDS
        )

        self.active_projects = (
            active_projects
            or _default_active_projects
        )

        self._loop_task: asyncio.Task | None = None

    async def start(self):

        if self._loop_task is not None:

            return

        self._loop_task = (
            asyncio.create_task(
                self._run_loop()
            )
        )

    async def stop(self):

        if self._loop_task is None:

            return

        self._loop_task.cancel()

        try:

            await self._loop_task

        except asyncio.CancelledError:

            pass

        self._loop_task = None

    async def _run_loop(self):

        while True:

            try:

                removed = self.cleanup_once()

                if removed:

                    logger.info(
                        "janitor removed %d stale project(s)",
                        removed
                    )

            except Exception:

                logger.exception(
                    "janitor cleanup failed"
                )

            await asyncio.sleep(
                self.interval
            )

    def cleanup_once(
        self
    ) -> int:

        if self.max_age <= 0:

            return 0

        now = time.time()

        active = self.active_projects()

        removed = 0

        for project_dir in sorted(
            self.repo.root.glob(
                "*"
            )
        ):

            if not project_dir.is_dir():

                continue

            project_id = (
                project_dir.name
            )

            if project_id in active:

                continue

            project_file = (
                project_dir
                / "project.json"
            )

            if not project_file.exists():

                shutil.rmtree(
                    project_dir,
                    ignore_errors=True
                )

                removed += 1

                continue

            age = (
                now
                - project_file.stat().st_mtime
            )

            if age <= self.max_age:

                continue

            shutil.rmtree(
                project_dir,
                ignore_errors=True
            )

            output_dir = (
                self.outputs.output_dir(
                    project_id
                )
            )

            if output_dir.exists():

                shutil.rmtree(
                    output_dir,
                    ignore_errors=True
                )

            removed += 1

        return removed


janitor = ProjectJanitor()
