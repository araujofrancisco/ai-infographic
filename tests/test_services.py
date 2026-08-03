import asyncio
import base64
from pathlib import Path

import pytest

from config import settings
from models import Section
from services import (
    ContentService,
    RenderingService
)

from helpers import (
    make_content
)

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGNUSLjD"
    "gA0wYRUdtBIAE4MBbE0AHosAAAAASUVORK5CYII="
)


def write_page_png(
    project_id: str
) -> Path:

    project_dir = (
        Path(
            settings.PROJECTS_DIR
        )
        / project_id
    )

    page_png = (
        project_dir
        / "page.png"
    )

    page_png.write_bytes(
        TINY_PNG
    )

    return page_png


def make_project(
    service: RenderingService,
    *,
    visual_descriptions=None
) -> str:

    content = make_content()

    content.sections = [
        Section(
            title=f"Section {index}",
            short_description="Description text.",
            bullet_points=[
                "Bullet one",
                "Bullet two"
            ],
            visual_description=(
                visual_descriptions
                and visual_descriptions[index]
            )
            or "An abstract subject."
        )
        for index in range(3)
    ]

    return service.repo.create_project(
        topic="Kubernetes",
        audience="Beginner",
        style="Minimal",
        content=content
    )


def test_build_page_prompt_includes_section_motifs():

    service = RenderingService()

    project_id = make_project(
        service,
        visual_descriptions=[
            "Connected nodes in a network mesh.",
            "Containers stacked like shipping crates.",
            "A radar scanning a cluster."
        ]
    )

    project = service.repo.load_project(
        project_id
    )

    prompt = service._build_page_prompt(
        project
    )

    assert "Section motifs" in prompt

    assert "network mesh" in prompt

    assert "shipping crates" in prompt

    assert "radar" in prompt

    assert (
        "LEFT 45%"
        in prompt
    )


def test_build_page_prompt_tolerates_legacy_project():

    service = RenderingService()

    project = {
        "topic": "Docker",
        "style": "Technical / Modern"
    }

    prompt = service._build_page_prompt(
        project
    )

    assert "Section motifs" not in prompt

    assert "Composition requirements" in prompt


def test_section_motifs_deduplicates_and_caps():

    service = RenderingService()

    project = {
        "content": {
            "sections": [
                {
                    "visual_description": "Same subject."
                },
                {
                    "visual_description": "same subject."
                },
                {
                    "visual_description": "A unique motif."
                }
            ]
        }
    }

    motifs = service._section_motifs(
        project
    )

    assert motifs == [
        "Same subject.",
        "A unique motif."
    ]


def test_create_content_persists_project(
    monkeypatch
):

    service = ContentService()

    calls = []

    async def fake_ollama(
        topic,
        audience,
        style,
        section_count
    ):

        calls.append(
            (
                topic,
                audience,
                style,
                section_count
            )
        )

        return make_content()

    monkeypatch.setattr(
        service.ollama,
        "generate_content",
        fake_ollama
    )

    def set_progress(
        current,
        total,
        message
    ):

        pass

    project_id, content = asyncio.run(
        service.create_content(
            topic="Docker",
            audience="Beginner",
            style="Minimal",
            section_count=4,
            set_progress=set_progress
        )
    )

    assert calls == [
        (
            "Docker",
            "Beginner",
            "Minimal",
            4
        )
    ]

    project = service.repo.load_project(
        project_id
    )

    assert project["topic"] == "Docker"

    assert content.title == "Test Infographic"


def test_generate_reuses_existing_page(
    monkeypatch
):

    service = RenderingService()

    project_id = make_project(
        service
    )

    page_png = write_page_png(
        project_id
    )

    comfy_calls = []

    async def fake_generate_image(
        prompt,
        negative_prompt,
        output_path,
        seed=None
    ):

        comfy_calls.append(
            output_path
        )

        Path(
            output_path
        ).write_bytes(
            TINY_PNG
        )

    def fake_render_infographic(
        content,
        image_paths,
        svg_path,
        png_path,
        pdf_path
    ):

        for path in [
            svg_path,
            png_path,
            pdf_path
        ]:

            path.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            path.write_bytes(
                b"x"
            )

    monkeypatch.setattr(
        service.comfyui,
        "generate_image",
        fake_generate_image
    )

    monkeypatch.setattr(
        service,
        "_prepare_page_image",
        lambda image_path: None
    )

    import services

    monkeypatch.setattr(
        services,
        "render_infographic",
        fake_render_infographic
    )

    result = asyncio.run(
        service.generate(
            project_id
        )
    )

    assert comfy_calls == []

    assert set(
        result
    ) == {
        "svg",
        "png",
        "pdf"
    }

    assert page_png.exists()


def test_generate_force_regenerates_page(
    monkeypatch
):

    service = RenderingService()

    project_id = make_project(
        service
    )

    write_page_png(
        project_id
    )

    comfy_calls = []

    async def fake_generate_image(
        prompt,
        negative_prompt,
        output_path,
        seed=None
    ):

        comfy_calls.append(
            output_path
        )

        Path(
            output_path
        ).write_bytes(
            TINY_PNG
        )

    def fake_render_infographic(
        content,
        image_paths,
        svg_path,
        png_path,
        pdf_path
    ):

        for path in [
            svg_path,
            png_path,
            pdf_path
        ]:

            path.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            path.write_bytes(
                b"x"
            )

    monkeypatch.setattr(
        service.comfyui,
        "generate_image",
        fake_generate_image
    )

    monkeypatch.setattr(
        service,
        "_prepare_page_image",
        lambda image_path: None
    )

    import services

    monkeypatch.setattr(
        services,
        "render_infographic",
        fake_render_infographic
    )

    asyncio.run(
        service.generate(
            project_id,
            force=True
        )
    )

    assert len(
        comfy_calls
    ) == 1


def test_generate_missing_project_raises():

    service = RenderingService()

    with pytest.raises(
        Exception
    ) as exc_info:

        asyncio.run(
            service.generate(
                "missing-project"
            )
        )

    assert "Project not found" in str(
        exc_info.value
    )
