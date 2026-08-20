import json
import logging
import time
from datetime import datetime
from pathlib import Path

from config import settings


logger = logging.getLogger(
    "infographic"
)


class TaskStore:

    def __init__(
        self,
        root: Path | None = None
    ):

        self.root = (
            root
            if root is not None
            else Path(
                settings.TASKS_DIR
            )
        )

        self.journal = (
            self.root
            / "journal.jsonl"
        )

    def append(
        self,
        snapshot: dict
    ):

        try:

            self.root.mkdir(
                parents=True,
                exist_ok=True
            )

            with open(
                self.journal,
                "a",
                encoding="utf-8"
            ) as file:

                file.write(
                    json.dumps(
                        snapshot,
                        ensure_ascii=False
                    )
                    + "\n"
                )

        except OSError as exc:

            logger.error(
                "could not journal task %s: %s",
                snapshot.get(
                    "id",
                    "?"
                ),
                exc
            )

    def read(
        self
    ) -> list[dict]:

        if not self.journal.exists():

            return []

        try:

            lines = self.journal.read_text(
                encoding="utf-8"
            ).splitlines()

        except OSError as exc:

            logger.error(
                "could not read task journal: %s",
                exc
            )

            return []

        snapshots = []

        for line in lines:

            line = line.strip()

            if not line:

                continue

            try:

                snapshots.append(
                    json.loads(
                        line
                    )
                )

            except json.JSONDecodeError:

                logger.warning(
                    "skipping corrupt journal entry"
                )

        return snapshots

    def recent(
        self,
        limit: int = 20
    ) -> list[dict]:

        return self.read()[-limit:]

    def journal_lines(
        self
    ) -> int:

        if not self.journal.exists():

            return 0

        try:

            return sum(
                1
                for line in self.journal.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            )

        except OSError:

            return 0

    def maybe_compact(
        self,
        max_age_seconds: int | None = None,
        threshold: int = 2000
    ) -> int:

        if self.journal_lines() < threshold:

            return 0

        return self.compact(
            max_age_seconds=max_age_seconds
        )

    def compact(
        self,
        max_age_seconds: int | None = None
    ) -> int:

        max_age = (
            max_age_seconds
            if max_age_seconds is not None
            else settings.TASK_TTL_SECONDS
        )

        latest: dict[str, dict] = {}

        started: dict[str, dict] = {}

        for snapshot in self.read():

            task_id = snapshot.get(
                "id"
            )

            if not task_id:

                continue

            ts = snapshot.get(
                "ts",
                ""
            )

            status = snapshot.get(
                "status"
            )

            if (
                status in (
                    "pending",
                    "running"
                )
                and ts
            ) and (
                task_id not in started
                or ts < started[task_id].get(
                    "ts",
                    ""
                )
            ):

                started[
                    task_id
                ] = snapshot

            if (
                task_id not in latest
                or ts >= latest[task_id].get(
                    "ts",
                    ""
                )
            ):

                latest[
                    task_id
                ] = snapshot

        kept = []

        for task_id, snapshot in latest.items():

            if (
                snapshot.get(
                    "status"
                )
                in (
                    "succeeded",
                    "failed",
                    "cancelled"
                )
            ):

                ts = snapshot.get(
                    "ts"
                )

                try:

                    age = (
                        time.time()
                        - datetime.fromisoformat(
                            ts
                        ).timestamp()
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    age = 0

                if age > max_age:

                    continue

            kept.append(
                snapshot
            )

            started_snapshot = (
                started.get(
                    task_id
                )
            )

            if (
                started_snapshot
                and started_snapshot
                is not snapshot
            ):

                kept.append(
                    started_snapshot
                )

        kept.sort(
            key=lambda item: (
                item.get(
                    "ts",
                    ""
                )
            )
        )

        removed = (
            self.journal_lines()
            - len(kept)
        )

        if removed <= 0:

            return 0

        self._rewrite(
            kept
        )

        return removed

    def delete(
        self,
        task_id: str
    ):

        snapshots = [
            snapshot
            for snapshot in self.read()
            if snapshot.get(
                "id"
            ) != task_id
        ]

        self._rewrite(
            snapshots
        )

    def _rewrite(
        self,
        snapshots: list[dict]
    ):

        try:

            self.root.mkdir(
                parents=True,
                exist_ok=True
            )

            with open(
                self.journal,
                "w",
                encoding="utf-8"
            ) as file:

                for snapshot in snapshots:

                    file.write(
                        json.dumps(
                            snapshot,
                            ensure_ascii=False
                        )
                        + "\n"
                    )

        except OSError as exc:

            logger.error(
                "could not rewrite task journal: %s",
                exc
            )
