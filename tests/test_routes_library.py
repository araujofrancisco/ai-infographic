import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from config import settings
from tasks import Task, task_manager

from helpers import iso_now, write_project

TESTED = set()


def make_project(
    *,
    topic: str,
    rendered: bool = False
) -> str:

    project_id = str(
        uuid.uuid4()
    )

    write_project(
        Path(
            settings.PROJECTS_DIR
        ),
        project_id,
        topic=topic,
        updated_at=iso_now()
    )

    if rendered:

        output_dir = (
            Path(
                settings.OUTPUT_DIR
            )
            / project_id
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        for ext in [
            "svg",
            "png",
            "pdf"
        ]:

            (
                output_dir
                / f"infographic.{ext}"
            ).write_bytes(
                b"x"
            )

    TESTED.add(
        project_id
    )

    return project_id


@pytest.fixture(autouse=True)
def cleanup_projects():

    yield

    for project_id in TESTED:

        for root in [
            Path(
                settings.PROJECTS_DIR
            ),
            Path(
                settings.OUTPUT_DIR
            )
        ]:

            target = (
                root
                / project_id
            )

            if target.exists():

                import shutil

                shutil.rmtree(
                    target,
                    ignore_errors=True
                )

    TESTED.clear()


@pytest.fixture
def client():

    with TestClient(
        main.app
    ) as test_client:

        yield test_client


def test_library_shows_rendered_and_draft(
    client
):

    rendered = make_project(
        topic="Rendered One",
        rendered=True
    )

    draft = make_project(
        topic="Draft One"
    )

    response = client.get(
        "/projects"
    )

    assert response.status_code == 200

    html = response.text

    assert "Library" in html

    assert "Rendered One" in html

    assert "Draft One" in html

    assert "Rendered" in html

    assert "Draft" in html

    assert (
        f"/projects/{rendered}/thumbnail"
        in html
    )

    assert (
        f"/projects/{draft}/thumbnail"
        not in html
    )

    assert (
        f"/result/{rendered}"
        in html
    )

    assert (
        f"/review/{draft}"
        in html
    )


def test_thumbnail_serves_rendered_png(
    client
):

    project_id = make_project(
        topic="Thumb",
        rendered=True
    )

    response = client.get(
        f"/projects/{project_id}/thumbnail"
    )

    assert response.status_code == 200

    assert response.content == b"x"


def test_thumbnail_404_when_no_preview(
    client
):

    project_id = make_project(
        topic="No Preview"
    )

    response = client.get(
        f"/projects/{project_id}/thumbnail"
    )

    assert response.status_code == 404


def test_delete_removes_project_and_outputs(
    client
):

    project_id = make_project(
        topic="Delete Me",
        rendered=True
    )

    response = client.post(
        f"/projects/{project_id}/delete"
    )

    assert response.status_code == 200

    assert response.json() == {
        "ok": True
    }

    assert not (
        Path(
            settings.PROJECTS_DIR
        )
        / project_id
    ).exists()

    assert not (
        Path(
            settings.OUTPUT_DIR
        )
        / project_id
    ).exists()


def test_delete_missing_returns_404(
    client
):

    response = client.post(
        f"/projects/{uuid.uuid4()}/delete"
    )

    assert response.status_code == 404


def test_delete_conflicts_with_active_task(
    client
):

    project_id = make_project(
        topic="Busy"
    )

    task = Task(
        id=str(
            uuid.uuid4()
        ),
        kind="infographic",
        form={
            "project_id": project_id
        }
    )

    task.status = "running"

    task_manager._tasks[
        task.id
    ] = task

    try:

        response = client.post(
            f"/projects/{project_id}/delete"
        )

        assert response.status_code == 409

        assert (
            Path(
                settings.PROJECTS_DIR
            )
            / project_id
        ).exists()

    finally:

        task_manager._tasks.pop(
            task.id,
            None
        )


def test_bad_project_id_is_rejected(
    client
):

    assert (
        client.get(
            "/projects/not-a-uuid/thumbnail"
        ).status_code
        == 404
    )

    assert (
        client.post(
            "/projects/not-a-uuid/delete"
        ).status_code
        == 404
    )


def test_activity_shows_journal_entries(
    client
):

    task_manager.store.append(
        {
            "id": str(
                uuid.uuid4()
            ),
            "kind": "content",
            "status": "failed",
            "error": "Ollama is not reachable",
            "project_id": None,
            "progress": {},
            "form": {
                "topic": "Kubernetes"
            },
            "created_at": 1.0,
            "started_at": 1.0,
            "finished_at": 2.0,
            "ts": "2026-08-03T10:00:00+00:00"
        }
    )

    response = client.get(
        "/activity"
    )

    assert response.status_code == 200

    html = response.text

    assert "Kubernetes" in html

    assert "Failed" in html

    assert "Ollama is not reachable" in html
