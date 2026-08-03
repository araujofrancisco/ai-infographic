from services import (
    ContentService,
    RenderingService
)


content_service = ContentService()

rendering_service = RenderingService()


async def content_worker(
    set_progress,
    *,
    topic: str,
    audience: str,
    style: str,
    section_count: int
) -> dict:

    project_id, _content = (
        await content_service.create_content(
            topic=topic,
            audience=audience,
            style=style,
            section_count=section_count,
            set_progress=set_progress
        )
    )

    return {
        "project_id": project_id
    }


async def infographic_worker(
    set_progress,
    *,
    project_id: str,
    force: bool = False
) -> dict:

    _files = await rendering_service.generate(
        project_id,
        force=force,
        set_progress=set_progress
    )

    return {
        "project_id": project_id
    }
