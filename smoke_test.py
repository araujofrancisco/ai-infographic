import ast
import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace


APP_DIR = Path(__file__).parent / "app"

os.environ.setdefault(
    "TASKS_DIR",
    str(
        Path(
            tempfile.mkdtemp(
                prefix="infographic-tasks-"
            )
        )
    )
)

MODULES = [
    "main",
    "config",
    "models",
    "ollama_client",
    "comfyui_client",
    "renderer",
    "storage",
    "services",
    "workers",
    "cleanup",
    "exceptions",
    "tasks",
    "routes_ui",
    "routes_tasks"
]

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGNUSLjD"
    "gA0wYRUdtBIAE4MBbE0AHosAAAAASUVORK5CYII="
)


def parse_all():

    for name in MODULES:

        source = (
            APP_DIR
            / f"{name}.py"
        ).read_text(
            encoding="utf-8"
        )

        ast.parse(source)

        print(f"OK   parse {name}")


def check_comfyui_structure():

    tree = ast.parse(
        (
            APP_DIR
            / "comfyui_client.py"
        ).read_text(
            encoding="utf-8"
        )
    )

    module_level = [
        node.name
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        )
    ]

    assert not module_level, (
        f"stray module-level functions: {module_level}"
    )

    class_def = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.ClassDef
        )
        and node.name == "ComfyUIClient"
    )

    body_names = [
        node.name
        for node in class_def.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        )
    ]

    for method in [
        "__init__",
        "build_workflow",
        "generate_image",
        "_post_prompt",
        "_wait_for_completion",
        "_find_output_image",
        "_download_image",
        "_status_error"
    ]:

        assert method in body_names, (
            f"missing method {method}"
        )

    build_workflow = next(
        node
        for node in class_def.body
        if isinstance(
            node,
            ast.FunctionDef
        )
        and node.name == "build_workflow"
    )

    nested = [
        node.name
        for node in ast.walk(build_workflow)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node is not build_workflow
    ]

    assert not nested, (
        f"unreachable functions nested in build_workflow: {nested}"
    )

    print("OK   comfyui_client structure")


def renderer_checks():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    if "pydantic" not in sys.modules:

        try:

            import pydantic  # noqa: F401

        except ImportError:

            pydantic = types.ModuleType(
                "pydantic"
            )

            pydantic.BaseModel = object
            pydantic.Field = (
                lambda **kwargs: None
            )
            pydantic.ValidationError = Exception

            sys.modules["pydantic"] = pydantic

    import renderer

    sections = [
        SimpleNamespace(
            title="Section One",
            short_description="A short description that is long enough to wrap across several lines and needs measuring.",
            bullet_points=[
                "First bullet point that also wraps to two lines",
                "Second bullet",
                "Third bullet"
            ]
        ),
        SimpleNamespace(
            title="Section Two",
            short_description="Another description.",
            bullet_points=[
                "Only bullet"
            ]
        )
    ]

    content = SimpleNamespace(
        title="Test Infographic",
        subtitle="A subtitle",
        sections=sections
    )

    with tempfile.TemporaryDirectory() as tmp:

        image_paths = []

        for index in range(
            len(sections)
        ):

            image_file = (
                Path(tmp)
                / f"section-{index + 1}.png"
            )

            image_file.write_bytes(
                TINY_PNG
            )

            image_paths.append(
                str(image_file)
            )

        svg = renderer.build_svg(
            content=content,
            image_paths=image_paths
        )

        assert (
            f'height="{renderer.PAGE_HEIGHT}"'
            in svg
        )

        assert (
            f'width="{renderer.PAGE_WIDTH}"'
            in svg
        )

        assert svg.count(
            "<image"
        ) == 1

        assert "<clipPath" not in svg

        assert "linearGradient" in svg

        assert "rgba(" in svg

        assert 'font-style="italic"' in svg

        assert "Example:" in svg

        assert "pageScrim" in svg

        assert "textScrim" in svg

        assert "<rect" in svg

        for title in [
            "Section One",
            "Section Two"
        ]:

            assert title in svg

    assert renderer._wrap(
        "",
        100,
        30
    ) == []

    wrapped = renderer._wrap(
        "word " * 100,
        max_width=400,
        font_size=30
    )

    assert len(wrapped) > 1

    print("OK   renderer build_svg")


def full_checks():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    import main

    from models import (
        InfographicContent,
        Section
    )

    from comfyui_client import (
        ComfyUIClient
    )

    from renderer import (
        render_infographic
    )

    content = InfographicContent(
        title="Test Infographic",
        subtitle="A subtitle",
        sections=[
            Section(
                title=f"Section {index}",
                short_description="Description text.",
                bullet_points=[
                    "Bullet one",
                    "Bullet two"
                ],
                visual_description="Illustration subject."
            )
            for index in range(3)
        ]
    )

    client = ComfyUIClient()

    workflow = client.build_workflow(
        prompt="positive prompt",
        negative_prompt="negative prompt",
        seed=42
    )

    assert workflow[
        "3"
    ]["inputs"]["text"] == "positive prompt"

    assert workflow[
        "4"
    ]["inputs"]["text"] == "negative prompt"

    assert workflow[
        "5"
    ]["inputs"]["seed"] == 42

    assert workflow[
        "13"
    ]["inputs"]["filename_prefix"] == (
        "infographic_illustration"
    )

    assert workflow is not client.workflow

    with tempfile.TemporaryDirectory() as tmp:

        base = Path(tmp)

        image_paths = []

        for index in range(3):

            image_file = (
                base
                / f"section-{index + 1}.png"
            )

            image_file.write_bytes(
                TINY_PNG
            )

            image_paths.append(
                str(image_file)
            )

        svg_path = base / "infographic.svg"
        png_path = base / "infographic.png"
        pdf_path = base / "infographic.pdf"

        render_infographic(
            content=content,
            image_paths=image_paths,
            svg_path=svg_path,
            png_path=png_path,
            pdf_path=pdf_path
        )

        for path in [
            svg_path,
            png_path,
            pdf_path
        ]:

            assert path.exists()

            assert (
                path.stat().st_size > 0
            )

    print("OK   full import + render")


def comfyui_error_detail_check():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    from comfyui_client import (
        ComfyUIClient
    )

    client = ComfyUIClient()

    detail = client._status_error(
        {
            "messages": [
                {
                    "type": "execution_error",
                    "message": {
                        "node_type": "KSampler",
                        "exception_message": "boom"
                    }
                }
            ]
        }
    )

    assert "KSampler" in detail

    assert "boom" in detail

    generic = client._status_error(
        {
            "messages": []
        }
    )

    assert "failed" in generic

    print("OK   comfyui error detail")


def ollama_retry_checks():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    from ollama_client import (
        OllamaClient
    )

    client = OllamaClient()

    calls = {
        "n": 0
    }

    async def fake_chat(
        messages
    ):

        calls["n"] += 1

        if calls["n"] == 1:

            return "not json at all"

        return json.dumps(
            {
                "title": "T",
                "subtitle": "S",
                "sections": [
                    {
                        "title": f"Section {index}",
                        "short_description": "d",
                        "bullet_points": [
                            "a",
                            "b"
                        ],
                        "visual_description": "v"
                    }
                    for index in range(3)
                ]
            }
        )

    client._chat = fake_chat

    async def scenario():

        content = await client.generate_content(
            "x",
            "Beginner",
            "Minimal",
            4
        )

        assert calls["n"] == 2

        assert content.title == "T"

    asyncio.run(
        scenario()
    )

    print("OK   ollama corrective retry")


def http_checks():

    from fastapi.testclient import TestClient

    import main

    from config import settings

    project_id = "test-project"

    project_dir = (
        Path(settings.PROJECTS_DIR)
        / project_id
    )

    project_dir.mkdir(
        parents=True
    )

    project_data = {
        "id": project_id,
        "topic": "Test",
        "audience": "Beginner",
        "style": "Minimal",
        "content": {
            "title": "Test Infographic",
            "subtitle": "Sub",
            "sections": [
                {
                    "title": f"Section {index}",
                    "short_description": "Description.",
                    "bullet_points": [
                        "Bullet one",
                        "Bullet two"
                    ],
                    "visual_description": "Illustration."
                }
                for index in range(3)
            ]
        }
    }

    (
        project_dir
        / "project.json"
    ).write_text(
        json.dumps(
            project_data
        ),
        encoding="utf-8"
    )

    output_dir = (
        Path(settings.OUTPUT_DIR)
        / project_id
    )

    output_dir.mkdir(
        parents=True
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
            TINY_PNG
        )

    client = TestClient(
        main.app
    )

    response = client.get(
        "/"
    )

    assert response.status_code == 200

    assert (
        "AI Infographic Generator"
        in response.text
    )

    response = client.get(
        f"/review/{project_id}"
    )

    assert response.status_code == 200

    assert (
        'id="content-title"'
        in response.text
    )

    assert (
        'class="sec-field sec-bullets"'
        in response.text
    )

    response = client.get(
        f"/result/{project_id}"
    )

    assert response.status_code == 200

    assert (
        "View PNG"
        in response.text
    )

    # TestClient does not pump asyncio background tasks created inside
    # handlers, so the queue flow is exercised against a live uvicorn.
    server = subprocess.Popen(
        [
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8092"
        ],
        cwd=str(
            APP_DIR
        ),
        env={
            **os.environ,
            "OLLAMA_URL": "http://127.0.0.1:1"
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:

        base_url = (
            "http://127.0.0.1:8092"
        )

        _wait_ready(
            base_url
        )

        form = urllib.parse.urlencode(
            {
                "topic": "Unreachable Ollama",
                "audience": "Beginner",
                "style": "Minimal",
                "section_count": "4"
            }
        ).encode()

        request = urllib.request.Request(
            f"{base_url}/generate-content",
            data=form,
            method="POST"
        )

        with urllib.request.urlopen(
            request
        ) as response:

            html = response.read().decode()

        assert "Working" in html

        match = re.search(
            r'var taskId = "([0-9a-f-]+)"',
            html
        )

        assert match, (
            "working.html missing task id"
        )

        task_id = match.group(1)

        status = None

        for _ in range(
            100
        ):

            time.sleep(
                0.2
            )

            with urllib.request.urlopen(
                f"{base_url}/tasks/{task_id}/status"
            ) as response:

                data = json.loads(
                    response.read().decode()
                )

            status = data["status"]

            if status in (
                "succeeded",
                "failed"
            ):

                break

        assert status == "failed", (
            status
        )

        with urllib.request.urlopen(
            f"{base_url}/tasks/{task_id}"
        ) as response:

            error_html = response.read().decode()

        assert (
            'class="error"'
            in error_html
        )

        assert (
            "Unreachable Ollama"
            in error_html
        )

        updated_content = {
            "title": "Updated Title",
            "subtitle": "Updated Subtitle",
            "sections": [
                {
                    "title": f"Section {index}",
                    "short_description": "Description.",
                    "bullet_points": [
                        "Bullet one",
                        "Bullet two"
                    ],
                    "visual_description": "Illustration."
                }
                for index in range(3)
            ]
        }

        save_form = urllib.parse.urlencode(
            {
                "project_id": project_id,
                "content_json": json.dumps(
                    updated_content
                )
            }
        ).encode()

        save_request = urllib.request.Request(
            f"{base_url}/save-content?json=1",
            data=save_form,
            method="POST"
        )

        with urllib.request.urlopen(
            save_request
        ) as response:

            save_data = json.loads(
                response.read().decode()
            )

        assert save_data[
            "ok"
        ] is True

        project_on_disk = json.loads(
            (
                Path(settings.PROJECTS_DIR)
                / project_id
                / "project.json"
            ).read_text(
                encoding="utf-8"
            )
        )

        assert project_on_disk[
            "content"
        ][
            "title"
        ] == "Updated Title"

        bad_form = urllib.parse.urlencode(
            {
                "project_id": project_id,
                "content_json": json.dumps(
                    {
                        "title": "x"
                    }
                )
            }
        ).encode()

        bad_request = urllib.request.Request(
            f"{base_url}/save-content?json=1",
            data=bad_form,
            method="POST"
        )

        try:

            with urllib.request.urlopen(
                bad_request
            ) as response:

                assert False, (
                    "invalid save should not succeed"
                )

        except urllib.error.HTTPError as exc:

            assert exc.code == 400

            bad_data = json.loads(
                exc.read().decode()
            )

            assert bad_data[
                "ok"
            ] is False

        form = urllib.parse.urlencode(
            {
                "project_id": project_id
            }
        ).encode()

        request = urllib.request.Request(
            f"{base_url}/generate-infographic",
            data=form,
            method="POST"
        )

        with urllib.request.urlopen(
            request
        ) as response:

            infographic_html = response.read().decode()

        match = re.search(
            r'var taskId = "([0-9a-f-]+)"',
            infographic_html
        )

        assert match

        infographic_task_id = match.group(1)

        status = None

        for _ in range(
            100
        ):

            time.sleep(
                0.2
            )

            with urllib.request.urlopen(
                f"{base_url}/tasks/{infographic_task_id}/status"
            ) as response:

                data = json.loads(
                    response.read().decode()
                )

            status = data["status"]

            if status in (
                "succeeded",
                "failed"
            ):

                break

        assert status == "failed", (
            status
        )

        # A failed infographic task must render the review error
        # page (200), not a 500 from a missing project_id.
        with urllib.request.urlopen(
            f"{base_url}/tasks/{infographic_task_id}"
        ) as response:

            infographic_error_html = (
                response.read().decode()
            )

        assert (
            'class="error"'
            in infographic_error_html
        )

    finally:

        server.terminate()

        try:

            server.wait(
                timeout=5
            )

        except subprocess.TimeoutExpired:

            server.kill()

    print("OK   http queue + result routes")


def _wait_ready(
    base_url: str
):

    for _ in range(
        100
    ):

        try:

            with urllib.request.urlopen(
                f"{base_url}/",
                timeout=1
            ) as response:

                if response.status == 200:

                    return

        except Exception:

            time.sleep(
                0.2
            )

    raise AssertionError(
        "server did not become ready"
    )


def tasks_checks():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    from tasks import TaskManager

    async def ok_worker(
        set_progress
    ):

        set_progress(
            0,
            2,
            "start"
        )

        await asyncio.sleep(
            0.01
        )

        set_progress(
            1,
            2,
            "mid"
        )

        return {
            "project_id": "abc"
        }

    async def fail_worker(
        set_progress
    ):

        from exceptions import GenerationError

        raise GenerationError(
            "boom"
        )

    async def scenario():

        manager = TaskManager()

        ok_id = manager.start(
            "content",
            ok_worker,
            form={
                "topic": "x"
            }
        )

        fail_id = manager.start(
            "infographic",
            fail_worker,
            form={
                "project_id": "p"
            }
        )

        await asyncio.sleep(
            0.05
        )

        ok_task = manager.get(
            ok_id
        )

        assert ok_task.status == (
            "succeeded"
        )

        assert ok_task.project_id == (
            "abc"
        )

        assert ok_task.result == {
            "project_id": "abc"
        }

        assert ok_task.progress == {
            "current": 1,
            "total": 2,
            "message": "mid"
        }

        fail_task = manager.get(
            fail_id
        )

        assert fail_task.status == (
            "failed"
        )

        assert fail_task.error == (
            "boom"
        )

        assert manager.get(
            "missing"
        ) is None

        data = manager.to_dict(
            ok_task
        )

        assert data[
            "status"
        ] == "succeeded"

        assert data[
            "progress"
        ][
            "current"
        ] == 1

    asyncio.run(
        scenario()
    )

    print("OK   task manager")


def tasks_queue_checks():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    from tasks import TaskManager

    async def slow_worker(
        set_progress
    ):

        await asyncio.sleep(
            0.3
        )

        return {
            "project_id": "x"
        }

    async def scenario():

        manager = TaskManager(
            max_queued_per_kind=1,
            max_age_seconds=1
        )

        first = manager.start(
            "content",
            slow_worker
        )

        assert manager.can_start(
            "content"
        ) is True

        second = manager.start(
            "content",
            slow_worker
        )

        assert manager.can_start(
            "content"
        ) is False

        assert manager.cancel(
            second
        ) is True

        assert manager.get(
            second
        ).status == "cancelled"

        assert manager.can_start(
            "content"
        ) is True

        started = {
            "flag": False
        }

        async def checkable_worker(
            set_progress
        ):

            started["flag"] = True

            await asyncio.sleep(
                0.1
            )

            set_progress(
                1,
                1,
                "done"
            )

            return {
                "project_id": "z"
            }

        run_id = manager.start(
            "infographic",
            checkable_worker
        )

        for _ in range(
            100
        ):

            if manager.get(
                run_id
            ).status == "running":

                break

            await asyncio.sleep(
                0.01
            )

        manager.cancel(
            run_id
        )

        for _ in range(
            100
        ):

            if manager.get(
                run_id
            ).status == "cancelled":

                break

            await asyncio.sleep(
                0.01
            )

        assert manager.get(
            run_id
        ).status == "cancelled"

        while manager.get(
            first
        ).status in (
            "pending",
            "running"
        ):

            await asyncio.sleep(
                0.01
            )

        manager.prune(
            max_age_seconds=0
        )

        assert manager.get(
            first
        ) is None

    asyncio.run(
        scenario()
    )

    print("OK   task queue + cancel + prune")


def tasks_coop_cancel_check():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    from tasks import TaskManager

    async def coop_worker(
        set_progress
    ):

        await asyncio.sleep(
            0.05
        )

        set_progress(
            1,
            1,
            "done"
        )

        return {
            "project_id": "c"
        }

    async def scenario():

        manager = TaskManager()

        task_id = manager.start(
            "content",
            coop_worker
        )

        for _ in range(
            100
        ):

            if manager.get(
                task_id
            ).status == "running":

                break

            await asyncio.sleep(
                0.01
            )

        task = manager.get(
            task_id
        )

        task.cancelled = True

        for _ in range(
            100
        ):

            if manager.get(
                task_id
            ).status in (
                "cancelled",
                "failed",
                "succeeded"
            ):

                break

            await asyncio.sleep(
                0.01
            )

        assert manager.get(
            task_id
        ).status == "cancelled"

    asyncio.run(
        scenario()
    )

    print("OK   task cooperative cancel")


def janitor_checks():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    from cleanup import (
        ProjectJanitor
    )

    from storage import (
        OutputStore,
        ProjectRepository
    )

    retention = (
        7 * 24 * 3600
    )

    old = (
        time.time()
        - 999999
    )

    with tempfile.TemporaryDirectory() as tmp:

        base = Path(
            tmp
        )

        projects = (
            base
            / "projects"
        )

        outputs = (
            base
            / "outputs"
        )

        projects.mkdir()

        outputs.mkdir()

        stale_id = (
            "stale-project"
        )

        stale_dir = (
            projects
            / stale_id
        )

        stale_dir.mkdir()

        stale_file = (
            stale_dir
            / "project.json"
        )

        stale_file.write_text(
            '{"id": "stale"}',
            encoding="utf-8"
        )

        os.utime(
            stale_file,
            (old, old)
        )

        stale_output = (
            outputs
            / stale_id
        )

        stale_output.mkdir()

        (
            stale_output
            / "infographic.png"
        ).write_bytes(
            b"x"
        )

        fresh_dir = (
            projects
            / "fresh-project"
        )

        fresh_dir.mkdir()

        (
            fresh_dir
            / "project.json"
        ).write_text(
            '{"id": "fresh"}',
            encoding="utf-8"
        )

        active_dir = (
            projects
            / "active-project"
        )

        active_dir.mkdir()

        active_file = (
            active_dir
            / "project.json"
        )

        active_file.write_text(
            '{"id": "active"}',
            encoding="utf-8"
        )

        os.utime(
            active_file,
            (old, old)
        )

        janitor = ProjectJanitor(
            repo=ProjectRepository(
                root=projects
            ),
            outputs=OutputStore(
                root=outputs
            ),
            max_age=retention,
            interval=3600,
            active_projects=lambda: {
                "active-project"
            }
        )

        removed = janitor.cleanup_once()

        assert removed == 1, (
            removed
        )

        assert not stale_dir.exists()

        assert not stale_output.exists()

        assert fresh_dir.exists()

        assert active_dir.exists()

        janitor.disabled = ProjectJanitor(
            repo=ProjectRepository(
                root=projects
            ),
            outputs=OutputStore(
                root=outputs
            ),
            max_age=0,
            active_projects=lambda: set()
        )

        assert (
            janitor.disabled.cleanup_once()
        ) == 0

        assert fresh_dir.exists()

    print("OK   project janitor")


def tasks_serialization_check():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    from tasks import TaskManager

    async def scenario():

        manager = TaskManager()

        counter = {
            "active": 0,
            "peak": 0
        }

        async def slow_worker(
            set_progress
        ):

            counter["active"] += 1

            counter["peak"] = max(
                counter["peak"],
                counter["active"]
            )

            await asyncio.sleep(
                0.05
            )

            counter["active"] -= 1

            return {
                "project_id": "abc"
            }

        ids = [
            manager.start(
                "content",
                slow_worker
            )
            for _ in range(3)
        ]

        while True:

            statuses = [
                manager.get(
                    task_id
                ).status
                for task_id in ids
            ]

            if all(
                status == "succeeded"
                for status in statuses
            ):

                break

            await asyncio.sleep(
                0.01
            )

        assert counter["peak"] == 1, (
            counter["peak"]
        )

        assert all(
            manager.get(
                task_id
            ).project_id == "abc"
            for task_id in ids
        )

    asyncio.run(
        scenario()
    )

    print("OK   task serialization")


def fit_checks():

    sys.path.insert(
        0,
        str(APP_DIR)
    )

    import renderer

    def make_section(
        index
    ):

        return SimpleNamespace(
            title=f"Section {index}",
            short_description=(
                "This section explains the core concept "
                "in a concise but complete way for the reader."
            ),
            bullet_points=[
                "Explains the fundamental idea behind the topic",
                "Shows a concrete example of how it is used",
                "Lists the main benefit for the reader",
                "Notes a common pitfall to avoid"
            ]
        )

    light = SimpleNamespace(
        title="Light",
        subtitle="Sub",
        sections=[
            SimpleNamespace(
                title="One",
                short_description="Short.",
                bullet_points=[
                    "a",
                    "b"
                ]
            )
        ]
    )

    dense = SimpleNamespace(
        title="Dense",
        subtitle="Sub",
        sections=[
            make_section(
                index
            )
            for index in range(8)
        ]
    )

    with tempfile.TemporaryDirectory() as tmp:

        paths = []

        for index in range(8):

            image_file = (
                Path(tmp)
                / f"section-{index + 1}.png"
            )

            image_file.write_bytes(
                TINY_PNG
            )

            paths.append(
                str(image_file)
            )

        assert renderer._fit_scale(
            light,
            paths[:1]
        ) == 1.0

        fit = renderer._fit_scale(
            dense,
            paths
        )

        assert (
            renderer.MIN_SCALE
            <= fit
            < 1.0
        ), fit

        height = renderer._layout_height(
            dense,
            paths,
            fit
        )

        assert (
            height
            <= (
                renderer.PAGE_HEIGHT
                - renderer.MARGIN
            )
        ), height

        svg = renderer.build_svg(
            dense,
            paths
        )

        assert (
            f'height="{renderer.PAGE_HEIGHT}"'
            in svg
        )

        for index in range(8):

            assert (
                f"Section {index}"
                in svg
            )

    print("OK   renderer scale-to-fit")


def main():

    parse_all()

    check_comfyui_structure()

    renderer_checks()

    tasks_checks()

    tasks_queue_checks()

    tasks_coop_cancel_check()

    tasks_serialization_check()

    fit_checks()

    janitor_checks()

    if "--full" in sys.argv:

        full_checks()

        comfyui_error_detail_check()

        ollama_retry_checks()

        http_checks()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":

    main()
