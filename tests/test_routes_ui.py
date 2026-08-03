import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
import workers
from config import settings
from tasks import Task, task_manager

from helpers import (
    iso_now,
    make_content,
    write_project
)

TESTED = set()


def cleanup():

    for task_id in TESTED:

        task_manager._tasks.pop(
            task_id,
            None
        )

    TESTED.clear()


@pytest.fixture(autouse=True)
def cleanup_tasks():

    yield

    cleanup()


@pytest.fixture
def client():

    with TestClient(
        main.app
    ) as test_client:

        yield test_client


def queue_kind(
    kind: str,
    count: int
) -> list[str]:

    ids = []

    for _index in range(
        count
    ):

        task_id = str(
            uuid.uuid4()
        )

        task = Task(
            id=task_id,
            kind=kind,
            form={}
        )

        task_manager._tasks[
            task_id
        ] = task

        TESTED.add(
            task_id
        )

        ids.append(
            task_id
        )

    return ids


def write_a_project() -> str:

    project_id = str(
        uuid.uuid4()
    )

    write_project(
        Path(
            settings.PROJECTS_DIR
        ),
        project_id,
        topic="Docker",
        updated_at=iso_now(),
        content=make_content().model_dump()
    )

    return project_id


def test_generate_content_queue_full_shows_error(
    client
):

    queue_kind(
        "content",
        1 + settings.MAX_QUEUED_PER_KIND
    )

    response = client.post(
        "/generate-content",
        data={
            "topic": "Kubernetes",
            "audience": "Beginner",
            "style": "Minimal",
            "section_count": 6
        }
    )

    assert response.status_code == 200

    html = response.text

    assert "queue is full" in html


def test_generate_content_starts_task_and_working_page(
    client,
    monkeypatch
):

    class FakeContentService:

        async def create_content(
            self,
            topic,
            audience,
            style,
            section_count,
            set_progress
        ):

            return "fake-project-id", make_content()

    monkeypatch.setattr(
        workers,
        "content_service",
        FakeContentService()
    )

    response = client.post(
        "/generate-content",
        data={
            "topic": "Docker",
            "audience": "Beginner",
            "style": "Minimal",
            "section_count": 6
        }
    )

    assert response.status_code == 200

    html = response.text

    assert "var taskId" in html

    match = re.search(
        r"var taskId = \"([^\"]+)\"",
        html
    )

    assert match is not None

    task_id = match.group(1)

    TESTED.add(
        task_id
    )

    assert (
        task_manager.get(
            task_id
        )
        is not None
    )


def test_save_content_json_valid_round_trip(
    client
):

    project_id = write_a_project()

    response = client.post(
        "/save-content?json=1",
        data={
            "project_id": project_id,
            "content_json": make_content(
                title="Edited Title"
            ).model_dump_json()
        }
    )

    assert response.status_code == 200

    assert response.json() == {
        "ok": True
    }

    project = (
        Path(
            settings.PROJECTS_DIR
        )
        / project_id
        / "project.json"
    )

    import json

    saved = json.loads(
        project.read_text(
            encoding="utf-8"
        )
    )

    assert (
        saved["content"]["title"]
        == "Edited Title"
    )


def test_save_content_json_invalid_returns_400(
    client
):

    project_id = write_a_project()

    response = client.post(
        "/save-content?json=1",
        data={
            "project_id": project_id,
            "content_json": '{"title": "only"}'
        }
    )

    assert response.status_code == 400

    body = response.json()

    assert body["ok"] is False

    assert "validation failed" in (
        body["error"].lower()
    )


def test_save_content_json_missing_project_returns_404(
    client
):

    response = client.post(
        "/save-content?json=1",
        data={
            "project_id": str(
                uuid.uuid4()
            ),
            "content_json": (
                make_content().model_dump_json()
            )
        }
    )

    assert response.status_code == 404

    assert response.json() == {
        "ok": False,
        "error": "Project not found."
    }


def test_review_404_for_missing_project(
    client
):

    response = client.get(
        f"/review/{uuid.uuid4()}"
    )

    assert response.status_code == 404


def test_preview_renders_svg(
    client
):

    project_id = write_a_project()

    response = client.post(
        f"/preview/{project_id}",
        data={
            "content_json": (
                make_content().model_dump_json()
            )
        }
    )

    assert response.status_code == 200

    assert (
        response.headers["content-type"]
        .startswith("image/svg+xml")
    )

    assert "<svg" in response.text

    assert (
        response.headers.get("cache-control")
        == "no-store"
    )


def test_preview_invalid_content_returns_400(
    client
):

    project_id = write_a_project()

    response = client.post(
        f"/preview/{project_id}",
        data={
            "content_json": '{"title": "only"}'
        }
    )

    assert response.status_code == 400

    body = response.json()

    assert body["ok"] is False

    assert "validation failed" in (
        body["error"].lower()
    )


def test_preview_missing_project_returns_404(
    client
):

    response = client.post(
        f"/preview/{uuid.uuid4()}",
        data={
            "content_json": (
                make_content().model_dump_json()
            )
        }
    )

    assert response.status_code == 404

    assert response.json() == {
        "ok": False,
        "error": "Project not found."
    }
