import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from config import settings
from models import InfographicContent


logger = logging.getLogger(
    "infographic"
)


class ProjectNotFound(FileNotFoundError):
    pass


def _now_iso() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


def _mtime_iso(
    path: Path
) -> str:

    return datetime.fromtimestamp(
        path.stat().st_mtime,
        tz=timezone.utc
    ).isoformat()


class ProjectRepository:

    def __init__(
        self,
        root: Path | None = None
    ):

        self.root = (
            root
            if root is not None
            else Path(
                settings.PROJECTS_DIR
            )
        )

    def project_dir(
        self,
        project_id: str
    ) -> Path:

        return (
            self.root
            / project_id
        )

    def project_file(
        self,
        project_id: str
    ) -> Path:

        return (
            self.project_dir(
                project_id
            )
            / "project.json"
        )

    def exists(
        self,
        project_id: str
    ) -> bool:

        if not project_id:

            return False

        return (
            self.project_file(
                project_id
            ).exists()
        )

    def load_project(
        self,
        project_id: str
    ) -> dict:

        if not self.exists(
            project_id
        ):

            raise ProjectNotFound(
                project_id
            )

        with open(
            self.project_file(
                project_id
            ),
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(
                file
            )

    def load_content(
        self,
        project_id: str
    ) -> InfographicContent | None:

        if not self.exists(
            project_id
        ):

            return None

        try:

            project = self.load_project(
                project_id
            )

            return InfographicContent.model_validate(
                project["content"]
            )

        except (
            json.JSONDecodeError,
            KeyError,
            ValidationError
        ) as exc:

            logger.error(
                "project %s is corrupt: %s",
                project_id,
                exc
            )

            return None

    def create_project(
        self,
        topic: str,
        audience: str,
        style: str,
        content: InfographicContent
    ) -> str:

        project_id = str(
            uuid.uuid4()
        )

        now = _now_iso()

        project = {
            "id": project_id,
            "topic": topic,
            "audience": audience,
            "style": style,
            "content": content.model_dump(),
            "created_at": now,
            "updated_at": now
        }

        self._save(
            project_id,
            project
        )

        return project_id

    def update_content(
        self,
        project_id: str,
        content: InfographicContent
    ):

        if not self.exists(
            project_id
        ):

            raise ProjectNotFound(
                project_id
            )

        project = self.load_project(
            project_id
        )

        project["content"] = (
            content.model_dump()
        )

        project["updated_at"] = (
            _now_iso()
        )

        self._save(
            project_id,
            project
        )

    def list_projects(
        self
    ) -> list[dict]:

        projects = []

        for project_dir in sorted(
            self.root.iterdir()
        ):

            if not project_dir.is_dir():

                continue

            name = project_dir.name

            try:

                parsed = uuid.UUID(
                    name
                )

            except ValueError:

                continue

            if str(
                parsed
            ) != name:

                continue

            project_file = (
                project_dir
                / "project.json"
            )

            if not project_file.exists():

                continue

            try:

                with open(
                    project_file,
                    "r",
                    encoding="utf-8"
                ) as file:

                    project = json.load(
                        file
                    )

            except (
                json.JSONDecodeError,
                OSError
            ) as exc:

                logger.error(
                    "project %s could not be listed: %s",
                    name,
                    exc
                )

                continue

            content = project.get(
                "content"
            )

            updated_at = project.get(
                "updated_at"
            ) or project.get(
                "created_at"
            )

            created_at = project.get(
                "created_at"
            ) or updated_at

            projects.append(
                {
                    "id": name,
                    "topic": project.get(
                        "topic",
                        ""
                    ),
                    "audience": project.get(
                        "audience",
                        ""
                    ),
                    "style": project.get(
                        "style",
                        ""
                    ),
                    "created_at": created_at,
                    "updated_at": (
                        updated_at
                        or _mtime_iso(
                            project_file
                        )
                    ),
                    "has_content": (
                        isinstance(
                            content,
                            dict
                        )
                    )
                }
            )

        return sorted(
            projects,
            key=lambda item: (
                item["updated_at"]
            ),
            reverse=True
        )

    def _save(
        self,
        project_id: str,
        project: dict
    ):

        project_dir = (
            self.project_dir(
                project_id
            )
        )

        project_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            self.project_file(
                project_id
            ),
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                project,
                file,
                indent=2,
                ensure_ascii=False
            )


class OutputStore:

    FILES = ("svg", "png", "pdf")

    def __init__(
        self,
        root: Path | None = None
    ):

        self.root = (
            root
            if root is not None
            else Path(
                settings.OUTPUT_DIR
            )
        )

    def output_dir(
        self,
        project_id: str
    ) -> Path:

        return (
            self.root
            / project_id
        )

    def file_path(
        self,
        project_id: str,
        ext: str
    ) -> Path:

        return (
            self.output_dir(
                project_id
            )
            / f"infographic.{ext}"
        )

    def files(
        self,
        project_id: str
    ) -> dict:

        return {
            ext: self.file_path(
                project_id,
                ext
            )
            for ext in self.FILES
        }

    def all_exist(
        self,
        project_id: str
    ) -> bool:

        return all(
            path.exists()
            for path in self.files(
                project_id
            ).values()
        )

    def resolve_file(
        self,
        project_id: str,
        filename: str
    ) -> Path | None:

        output_dir = (
            self.output_dir(
                project_id
            ).resolve()
        )

        target = (
            output_dir
            / filename
        ).resolve()

        if not str(
            target
        ).startswith(
            str(
                output_dir
            )
        ):

            return None

        if not (
            target.exists()
            and target.is_file()
        ):

            return None

        return target
