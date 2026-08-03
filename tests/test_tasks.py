import asyncio

from task_store import TaskStore
from tasks import INTERRUPTED_MESSAGE, TaskManager


def test_journal_records_lifecycle(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    async def scenario():

        manager = TaskManager(
            store=store,
            max_age_seconds=600
        )

        async def ok_worker(
            set_progress
        ):

            return {
                "project_id": "abc"
            }

        task_id = manager.start(
            "content",
            ok_worker,
            form={
                "topic": "x"
            }
        )

        await asyncio.sleep(
            0.05
        )

        assert manager.get(
            task_id
        ).status == "succeeded"

    asyncio.run(
        scenario()
    )

    statuses = [
        snapshot["status"]
        for snapshot in store.read()
    ]

    assert statuses == [
        "pending",
        "running",
        "succeeded"
    ]

    assert store.read()[0]["form"] == {
        "topic": "x"
    }


def test_restore_marks_interrupted_as_failed(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    store.append(
        {
            "id": "inflight",
            "kind": "infographic",
            "status": "running",
            "result": {},
            "error": None,
            "project_id": "p2",
            "progress": {},
            "form": {
                "project_id": "p2"
            },
            "created_at": 1.0,
            "started_at": 1.0,
            "finished_at": None,
            "ts": "2026-08-03T10:00:00+00:00"
        }
    )

    manager = TaskManager(
        store=store,
        max_age_seconds=600
    )

    assert manager.restore() == 1

    task = manager.get(
        "inflight"
    )

    assert task.status == "failed"

    assert task.error == INTERRUPTED_MESSAGE

    assert task.project_id == "p2"

    assert manager.restore() == 0


def test_restore_replays_terminal_state(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    store.append(
        {
            "id": "done",
            "kind": "content",
            "status": "succeeded",
            "result": {
                "project_id": "p1"
            },
            "error": None,
            "project_id": "p1",
            "progress": {},
            "form": {
                "topic": "x"
            },
            "created_at": 1.0,
            "started_at": 1.0,
            "finished_at": 2.0,
            "ts": "2026-08-03T10:00:00+00:00"
        }
    )

    manager = TaskManager(
        store=store,
        max_age_seconds=600
    )

    manager.restore()

    task = manager.get(
        "done"
    )

    assert task.status == "succeeded"

    assert task.project_id == "p1"

    assert (
        manager.can_start(
            "content"
        )
        is True
    )


def test_prune_removes_restored_tasks(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    store.append(
        {
            "id": "old",
            "kind": "content",
            "status": "succeeded",
            "result": {
                "project_id": "p"
            },
            "error": None,
            "project_id": "p",
            "progress": {},
            "form": {},
            "created_at": 1.0,
            "started_at": 1.0,
            "finished_at": 2.0,
            "ts": "2026-08-03T10:00:00+00:00"
        }
    )

    manager = TaskManager(
        store=store,
        max_age_seconds=0
    )

    manager.restore()

    manager.prune()

    assert manager.get(
        "old"
    ) is None


def test_append_failure_does_not_break_worker(
    tmp_path
):

    blocker = (
        tmp_path
        / "tasks"
    )

    blocker.write_text(
        "i am a file"
    )

    store = TaskStore(
        root=blocker
    )

    store.append(
        {
            "id": "x"
        }
    )

    async def scenario():

        manager = TaskManager(
            store=store,
            max_age_seconds=600
        )

        async def ok_worker(
            set_progress
        ):

            return {
                "project_id": "p"
            }

        task_id = manager.start(
            "content",
            ok_worker
        )

        await asyncio.sleep(
            0.05
        )

        assert manager.get(
            task_id
        ).status == "succeeded"

    asyncio.run(
        scenario()
    )


def test_store_recent_returns_tail(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    for index in range(5):

        store.append(
            {
                "id": f"t{index}",
                "status": "succeeded"
            }
        )

    recent = store.recent(
        limit=2
    )

    assert [
        entry["id"]
        for entry in recent
    ] == [
        "t3",
        "t4"
    ]
