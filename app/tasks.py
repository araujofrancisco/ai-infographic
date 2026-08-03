import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

from config import settings
from exceptions import GenerationError
from task_store import TaskStore


logger = logging.getLogger(
    "infographic"
)

INTERRUPTED_MESSAGE = (
    "The server restarted while this task was running. "
    "Please start it again."
)


class TaskCancelled(Exception):
    pass


class QueueFullError(Exception):

    def __init__(
        self,
        kind: str
    ):

        self.kind = kind

        super().__init__(
            f"too many queued tasks of kind {kind}"
        )


ProgressCallback = Callable[
    [
        int,
        int,
        str
    ],
    None
]


@dataclass
class Task:

    id: str
    kind: str
    form: dict
    status: str = "pending"
    result: dict = field(
        default_factory=dict
    )
    error: str | None = None
    project_id: str | None = None
    progress: dict = field(
        default_factory=dict
    )
    cancelled: bool = False
    coro: "asyncio.Task | None" = field(
        default=None,
        repr=False
    )
    created_at: float = field(
        default_factory=time.monotonic
    )
    started_at: float | None = None
    finished_at: float | None = None


class TaskManager:

    def __init__(
        self,
        max_queued_per_kind: int | None = None,
        max_age_seconds: int | None = None,
        store: TaskStore | None = None
    ):

        self._tasks: dict[str, Task] = {}

        self._slots: dict[str, asyncio.Semaphore] = {}

        self.store = (
            store
            if store is not None
            else TaskStore()
        )

        self._restored = False

        self.max_queued = (
            max_queued_per_kind
            if max_queued_per_kind is not None
            else settings.MAX_QUEUED_PER_KIND
        )

        self.max_age = (
            max_age_seconds
            if max_age_seconds is not None
            else settings.TASK_TTL_SECONDS
        )

    def can_start(
        self,
        kind: str
    ) -> bool:

        active = sum(
            1
            for task in self._tasks.values()
            if task.kind == kind
            and task.status in (
                "pending",
                "running"
            )
        )

        return active < (
            1
            + self.max_queued
        )

    def start(
        self,
        kind: str,
        worker: Callable[
            [ProgressCallback],
            Awaitable[dict]
        ],
        form: dict | None = None
    ) -> str:

        self.prune()

        if not self.can_start(
            kind
        ):

            raise QueueFullError(
                kind
            )

        task = Task(
            id=str(
                uuid.uuid4()
            ),
            kind=kind,
            form=form or {}
        )

        self._tasks[
            task.id
        ] = task

        slot = self._slots.setdefault(
            kind,
            asyncio.Semaphore(
                1
            )
        )

        asyncio_task = (
            asyncio.get_running_loop().create_task(
                self._run(
                    task,
                    worker,
                    slot
                )
            )
        )

        task.coro = asyncio_task

        self.store.append(
            self._snapshot(
                task
            )
        )

        return task.id

    def get(
        self,
        task_id: str
    ) -> Task | None:

        self.prune()

        return self._tasks.get(
            task_id
        )

    def cancel(
        self,
        task_id: str
    ) -> bool:

        task = self._tasks.get(
            task_id
        )

        if task is None:

            return False

        if task.status not in (
            "pending",
            "running"
        ):

            return False

        task.cancelled = True

        if (
            task.coro is not None
            and not task.coro.done()
        ):

            task.coro.cancel()

        if task.status == "pending":

            task.status = "cancelled"

            task.error = (
                "Task was cancelled."
            )

            task.finished_at = (
                time.monotonic()
            )

            self.store.append(
                self._snapshot(
                    task
                )
            )

        return True

    def active_project_ids(
        self
    ) -> set[str]:

        active = set()

        for task in self._tasks.values():

            if task.status not in (
                "pending",
                "running"
            ):

                continue

            project_id = (
                task.project_id
                or task.form.get(
                    "project_id"
                )
            )

            if project_id:

                active.add(
                    project_id
                )

        return active

    def prune(
        self,
        max_age_seconds: int | None = None
    ) -> int:

        max_age = (
            max_age_seconds
            if max_age_seconds is not None
            else self.max_age
        )

        now = time.monotonic()

        stale = [
            task_id
            for task_id, task in self._tasks.items()
            if task.status in (
                "succeeded",
                "failed",
                "cancelled"
            )
            and task.finished_at is not None
            and (
                now - task.finished_at
            ) > max_age
        ]

        for task_id in stale:

            del self._tasks[
                task_id
            ]

        return len(
            stale
        )

    def to_dict(
        self,
        task: Task
    ) -> dict:

        return {
            "id": task.id,
            "kind": task.kind,
            "status": task.status,
            "result": task.result,
            "error": task.error,
            "project_id": task.project_id,
            "progress": task.progress,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "finished_at": task.finished_at
        }

    def _snapshot(
        self,
        task: Task
    ) -> dict:

        snapshot = self.to_dict(
            task
        )

        snapshot["form"] = (
            task.form
        )

        snapshot["ts"] = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        return snapshot

    def restore(
        self
    ) -> int:

        if self._restored:

            return 0

        self._restored = True

        now = time.monotonic()

        latest: dict[str, dict] = {}

        for snapshot in self.store.read():

            latest[
                snapshot.get(
                    "id"
                )
            ] = snapshot

        restored = 0

        for task_id, snapshot in latest.items():

            if not task_id:

                continue

            status = snapshot.get(
                "status"
            )

            task = Task(
                id=task_id,
                kind=snapshot.get(
                    "kind",
                    ""
                ),
                form=snapshot.get(
                    "form",
                    {}
                )
            )

            task.project_id = (
                snapshot.get(
                    "project_id"
                )
            )

            task.result = (
                snapshot.get(
                    "result",
                    {}
                )
            )

            task.progress = (
                snapshot.get(
                    "progress",
                    {}
                )
            )

            if status in (
                "pending",
                "running"
            ):

                task.status = "failed"

                task.error = INTERRUPTED_MESSAGE

                logger.info(
                    "task %s (%s) interrupted by restart",
                    task_id,
                    task.kind
                )

            else:

                task.status = status

                task.error = (
                    snapshot.get(
                        "error"
                    )
                )

            task.created_at = now

            task.started_at = now

            task.finished_at = now

            self._tasks[
                task_id
            ] = task

            restored += 1

        return restored

    def _progress_for(
        self,
        task: Task
    ) -> ProgressCallback:

        def set_progress(
            current: int,
            total: int,
            message: str = ""
        ):

            if task.cancelled:

                raise TaskCancelled()

            task.progress = {
                "current": current,
                "total": total,
                "message": message
            }

        return set_progress

    async def _run(
        self,
        task: Task,
        worker: Callable[
            [ProgressCallback],
            Awaitable[dict]
        ],
        slot: asyncio.Semaphore
    ):

        async with slot:

            if task.cancelled:

                task.status = "cancelled"

                task.error = (
                    "Task was cancelled."
                )

                task.finished_at = (
                    time.monotonic()
                )

                return

            task.status = "running"

            task.started_at = (
                time.monotonic()
            )

            self.store.append(
                self._snapshot(
                    task
                )
            )

            logger.info(
                "task %s (%s) started",
                task.id,
                task.kind
            )

            try:

                result = await worker(
                    self._progress_for(
                        task
                    )
                )

                task.result = result

                task.project_id = result.get(
                    "project_id"
                )

                task.status = "succeeded"

            except asyncio.CancelledError:

                task.status = "cancelled"

                task.error = (
                    "Task was cancelled."
                )

            except TaskCancelled:

                task.status = "cancelled"

                task.error = (
                    "Task was cancelled."
                )

            except GenerationError as exc:

                task.status = "failed"

                task.error = exc.message

            except Exception as exc:

                task.status = "failed"

                logger.exception(
                    "task %s (%s) failed unexpectedly: %s",
                    task.id,
                    task.kind,
                    exc
                )

                task.error = (
                    "Unexpected error. "
                    "Check the server logs for details."
                )

            task.finished_at = (
                time.monotonic()
            )

            self.store.append(
                self._snapshot(
                    task
                )
            )

            logger.info(
                "task %s (%s) %s in %.1fs",
                task.id,
                task.kind,
                task.status,
                task.finished_at
                - (
                    task.started_at
                    or task.finished_at
                )
            )


task_manager = TaskManager()
