import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
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


def add_task(
    kind: str,
    *,
    form: dict
) -> str:

    task_id = str(
        uuid.uuid4()
    )

    task = Task(
        id=task_id,
        kind=kind,
        form=form
    )

    task.status = "failed"

    task.error = "Something went wrong."

    task_manager._tasks[
        task_id
    ] = task

    TESTED.add(
        task_id
    )

    return task_id


def test_content_error_page_offers_retry(
    client
):

    task_id = add_task(
        "content",
        form={
            "topic": "Docker",
            "audience": "Beginner",
            "style": "Minimal",
            "section_count": 6
        }
    )

    response = client.get(
        f"/tasks/{task_id}"
    )

    assert response.status_code == 200

    html = response.text

    assert "Something went wrong." in html

    assert "Try generating content again" in html

    assert 'action="/generate-content"' in html

    assert 'name="topic"' in html

    assert 'value="Docker"' in html

    assert 'name="section_count"' in html


def test_infographic_error_page_offers_retry(
    client
):

    project_id = str(
        uuid.uuid4()
    )

    write_project(
        Path(
            settings.PROJECTS_DIR
        ),
        project_id,
        topic="Kubernetes",
        updated_at=iso_now(),
        content=make_content().model_dump()
    )

    task_id = add_task(
        "infographic",
        form={
            "project_id": project_id,
            "force": True
        }
    )

    response = client.get(
        f"/tasks/{task_id}"
    )

    assert response.status_code == 200

    html = response.text

    assert (
        "Try generating the infographic again"
        in html
    )

    assert (
        'action="/generate-infographic"'
        in html
    )

    assert 'name="project_id"' in html

    assert (
        f'value="{project_id}"'
        in html
    )

    assert 'name="force"' in html

    assert 'value="1"' in html


def test_task_page_404_for_missing_task(
    client
):

    response = client.get(
        f"/tasks/{uuid.uuid4()}"
    )

    assert response.status_code == 404
