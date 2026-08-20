import asyncio
from datetime import datetime, timedelta, timezone

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


def test_task_times_out_marks_failed(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    async def scenario():

        manager = TaskManager(
            store=store,
            max_age_seconds=600,
            content_timeout_seconds=0.1
        )

        async def stuck_worker(
            set_progress
        ):

            await asyncio.sleep(10)

            return {}

        task_id = manager.start(
            "content",
            stuck_worker
        )

        await asyncio.sleep(0.4)

        task = manager.get(
            task_id
        )

        assert task.status == "failed"

        assert (
            "did not finish within"
            in (
                task.error
                or ""
            )
        )

        assert task.finished_at is not None

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


def _snapshot(
    task_id: str,
    status: str,
    ts: str
) -> dict:

    return {
        "id": task_id,
        "kind": "content",
        "status": status,
        "result": {},
        "error": None,
        "project_id": None,
        "progress": {},
        "form": {},
        "created_at": 1.0,
        "started_at": 1.0,
        "finished_at": 2.0,
        "ts": ts
    }


def _recent_ts() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


def _later_ts(
    earlier: str
) -> str:

    return (
        datetime.fromisoformat(
            earlier
        ) + timedelta(
            seconds=1
        )
    ).isoformat()


def test_compact_drops_stale_and_collapses_lifecycle(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    pending_ts = _recent_ts()

    running_ts = _later_ts(
        pending_ts
    )

    done_ts = _later_ts(
        running_ts
    )

    store.append(
        _snapshot(
            "fresh",
            "pending",
            pending_ts
        )
    )

    store.append(
        _snapshot(
            "fresh",
            "running",
            running_ts
        )
    )

    store.append(
        _snapshot(
            "fresh",
            "succeeded",
            done_ts
        )
    )

    store.append(
        _snapshot(
            "old",
            "succeeded",
            "2026-01-01T00:00:00+00:00"
        )
    )

    removed = store.compact(
        max_age_seconds=600
    )

    assert removed == 2

    kept = store.read()

    assert {
        entry["id"]
        for entry in kept
    } == {
        "fresh"
    }

    assert {
        entry["status"]
        for entry in kept
    } == {
        "pending",
        "succeeded"
    }


def test_compact_keeps_started_snapshot_for_activity(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    running_ts = _recent_ts()

    done_ts = _later_ts(
        running_ts
    )

    store.append(
        _snapshot(
            "done",
            "running",
            running_ts
        )
    )

    store.append(
        _snapshot(
            "done",
            "succeeded",
            done_ts
        )
    )

    store.compact(
        max_age_seconds=600
    )

    statuses = {
        entry["status"]
        for entry in store.read()
    }

    assert statuses == {
        "running",
        "succeeded"
    }


def test_compact_keeps_interrupted_non_terminal(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    store.append(
        _snapshot(
            "inflight",
            "running",
            "2026-01-01T00:00:00+00:00"
        )
    )

    removed = store.compact(
        max_age_seconds=600
    )

    assert removed == 0

    assert (
        store.read()[0]["status"]
        == "running"
    )


def test_maybe_compact_respects_threshold(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    recent = _recent_ts()

    for index in range(10):

        store.append(
            _snapshot(
                f"t{index}",
                "pending",
                recent
            )
        )

        store.append(
            _snapshot(
                f"t{index}",
                "running",
                recent
            )
        )

        store.append(
            _snapshot(
                f"t{index}",
                "succeeded",
                recent
            )
        )

    assert store.maybe_compact(
        threshold=1000
    ) == 0

    assert store.journal_lines() == 30

    assert store.maybe_compact(
        threshold=5
    ) == 10

    assert store.journal_lines() == 20


def test_restore_journals_interrupted_as_failed(
    tmp_path
):

    store = TaskStore(
        root=tmp_path
        / "tasks"
    )

    store.append(
        _snapshot(
            "inflight",
            "running",
            "2026-01-01T00:00:00+00:00"
        )
    )

    manager = TaskManager(
        store=store,
        max_age_seconds=600
    )

    manager.restore()

    tail = store.read()[-1]

    assert tail["id"] == "inflight"

    assert tail["status"] == "failed"

    assert tail["error"] == INTERRUPTED_MESSAGE
