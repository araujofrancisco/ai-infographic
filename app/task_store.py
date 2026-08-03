import json
import logging
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
