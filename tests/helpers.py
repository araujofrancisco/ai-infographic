import json
from datetime import datetime, timezone

from models import InfographicContent, Section


def make_content(
    title: str = "Test Infographic"
) -> InfographicContent:

    return InfographicContent(
        title=title,
        subtitle="A subtitle",
        sections=[
            Section(
                title=f"Section {index}",
                short_description="A short description.",
                bullet_points=[
                    "Bullet one",
                    "Bullet two"
                ],
                visual_description="An illustration subject."
            )
            for index in range(3)
        ]
    )


def write_project(
    root,
    project_id: str,
    *,
    topic: str = "Topic",
    style: str = "Minimal",
    updated_at: str,
    content: dict | None = None
):

    project_dir = (
        root
        / project_id
    )

    project_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    project = {
        "id": project_id,
        "topic": topic,
        "style": style,
        "content": content
        or make_content().model_dump(),
        "created_at": updated_at,
        "updated_at": updated_at
    }

    (
        project_dir
        / "project.json"
    ).write_text(
        json.dumps(
            project,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    return project_dir


def iso_now() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()
