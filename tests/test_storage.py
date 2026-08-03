import json
from pathlib import Path

from storage import ProjectRepository

from helpers import iso_now, make_content, write_project


def test_create_project_adds_timestamps(
    tmp_path
):

    repo = ProjectRepository(
        root=tmp_path
        / "projects"
    )

    project_id = repo.create_project(
        "Topic",
        "Beginner",
        "Minimal",
        make_content()
    )

    project = repo.load_project(
        project_id
    )

    assert project["created_at"]

    assert (
        project["updated_at"]
        == project["created_at"]
    )


def test_update_content_bumps_updated_at(
    tmp_path
):

    repo = ProjectRepository(
        root=tmp_path
        / "projects"
    )

    project_id = repo.create_project(
        "Topic",
        "Beginner",
        "Minimal",
        make_content()
    )

    first = repo.load_project(
        project_id
    )["updated_at"]

    repo.update_content(
        project_id,
        make_content(
            title="Changed"
        )
    )

    second = repo.load_project(
        project_id
    )["updated_at"]

    assert second >= first

    assert (
        repo.load_content(
            project_id
        ).title
        == "Changed"
    )


def test_list_projects_orders_by_updated_at(
    tmp_path
):

    root = (
        tmp_path
        / "projects"
    )

    write_project(
        root,
        "11111111-1111-1111-1111-111111111111",
        topic="Older",
        updated_at="2026-01-01T00:00:00+00:00"
    )

    write_project(
        root,
        "22222222-2222-2222-2222-222222222222",
        topic="Newer",
        updated_at="2026-06-01T00:00:00+00:00"
    )

    repo = ProjectRepository(
        root=root
    )

    projects = repo.list_projects()

    assert [
        project["topic"]
        for project in projects
    ] == [
        "Newer",
        "Older"
    ]

    assert projects[0]["has_content"] is True


def test_list_projects_skips_foreign_and_corrupt(
    tmp_path
):

    root = (
        tmp_path
        / "projects"
    )

    write_project(
        root,
        "11111111-1111-1111-1111-111111111111",
        topic="Valid",
        updated_at=iso_now()
    )

    (root / "not-a-uuid").mkdir()

    (
        root
        / "not-a-uuid"
        / "project.json"
    ).write_text(
        "{}",
        encoding="utf-8"
    )

    (root / "22222222-2222-2222-2222-222222222222").mkdir()

    (
        root
        / "22222222-2222-2222-2222-222222222222"
        / "project.json"
    ).write_text(
        "{not json",
        encoding="utf-8"
    )

    (root / "empty-dir").mkdir()

    projects = ProjectRepository(
        root=root
    ).list_projects()

    assert [
        project["topic"]
        for project in projects
    ] == [
        "Valid"
    ]


def test_list_projects_falls_back_to_mtime(
    tmp_path
):

    root = (
        tmp_path
        / "projects"
    )

    project_dir = (
        root
        / "11111111-1111-1111-1111-111111111111"
    )

    project_dir.mkdir(
        parents=True
    )

    project = {
        "id": "11111111-1111-1111-1111-111111111111",
        "topic": "Legacy"
    }

    (
        project_dir
        / "project.json"
    ).write_text(
        json.dumps(
            project
        ),
        encoding="utf-8"
    )

    projects = ProjectRepository(
        root=root
    ).list_projects()

    assert len(projects) == 1

    assert (
        projects[0]["updated_at"]
        is not None
    )


def test_load_content_is_none_for_missing():

    repo = ProjectRepository(
        root=Path(
            "/tmp"
        )
    )

    assert repo.load_content(
        "missing-project"
    ) is None
