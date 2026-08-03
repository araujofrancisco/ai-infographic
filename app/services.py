import asyncio

from models import InfographicContent
from ollama_client import OllamaClient
from comfyui_client import ComfyUIClient
from renderer import render_infographic
from storage import OutputStore, ProjectNotFound, ProjectRepository
from exceptions import GenerationError


NEGATIVE_PROMPT = """
text,
letters,
words,
numbers,
symbols,
characters,
typography,
font,
labels,
caption,
captions,
title text,
signage,
sign,
signs,
banner,
banners,
writing,
lettering,
scribbles,
calligraphy,
handwriting,
watermark,
logo,
gibberish,
unreadable text,
text-like marks,
noise,
blurry,
low quality,
distorted,
messy composition
"""


class ContentService:

    def __init__(self):

        self.ollama = OllamaClient()

        self.repo = ProjectRepository()

    async def create_content(
        self,
        topic: str,
        audience: str,
        style: str,
        section_count: int,
        set_progress
    ):

        set_progress(
            current=0,
            total=1,
            message="Generating content with Ollama…"
        )

        content = await self.ollama.generate_content(
            topic=topic,
            audience=audience,
            style=style,
            section_count=section_count
        )

        project_id = self.repo.create_project(
            topic=topic,
            audience=audience,
            style=style,
            content=content
        )

        set_progress(
            current=1,
            total=1,
            message="Content ready"
        )

        return project_id, content

    def save_content(
        self,
        project_id: str,
        content: InfographicContent
    ):

        self.repo.update_content(
            project_id,
            content
        )


class RenderingService:

    def __init__(self):

        self.comfyui = ComfyUIClient()

        self.repo = ProjectRepository()

        self.outputs = OutputStore()

    async def generate(
        self,
        project_id: str,
        *,
        force: bool = False,
        set_progress=None
    ):

        if set_progress is None:

            set_progress = (
                lambda *args, **kwargs: None
            )

        try:

            project = self.repo.load_project(
                project_id
            )

        except ProjectNotFound as exc:

            raise GenerationError(
                "Project not found."
            ) from exc

        content = InfographicContent.model_validate(
            project["content"]
        )

        project_dir = self.repo.project_dir(
            project_id
        )

        total = 2

        set_progress(
            current=0,
            total=total,
            message="Rendering full-page illustration…"
        )

        image_path = (
            project_dir
            / "page.png"
        )

        if (
            not force
            and image_path.exists()
            and image_path.stat().st_size > 0
        ):

            pass

        else:

            prompt = self._build_page_prompt(
                project
            )

            await self.comfyui.generate_image(
                prompt=prompt,
                negative_prompt=NEGATIVE_PROMPT,
                output_path=str(
                    image_path
                )
            )

        await asyncio.to_thread(
            self._prepare_page_image,
            image_path
        )

        set_progress(
            current=1,
            total=total,
            message="Rendering PDF…"
        )

        svg_path = self.outputs.file_path(
            project_id,
            "svg"
        )

        png_path = self.outputs.file_path(
            project_id,
            "png"
        )

        pdf_path = self.outputs.file_path(
            project_id,
            "pdf"
        )

        await asyncio.to_thread(
            render_infographic,
            content=content,
            image_paths=[str(image_path)],
            svg_path=svg_path,
            png_path=png_path,
            pdf_path=pdf_path
        )

        return {
            "svg": str(svg_path),
            "png": str(png_path),
            "pdf": str(pdf_path)
        }

    @staticmethod
    def _prepare_page_image(
        image_path
    ):

        from PIL import Image, ImageFilter

        img = Image.open(
            image_path
        ).convert("RGB")

        width, height = img.size

        fade_from = int(
            width * 0.42
        )

        fade_to = int(
            width * 0.56
        )

        blurred = img.filter(
            ImageFilter.GaussianBlur(
                radius=max(
                    8,
                    int(
                        width * 0.04
                    )
                )
            )
        )

        mask_row = [
            255
            if x < fade_from
            else int(
                255
                * max(
                    0.0,
                    1
                    - (x - fade_from)
                    / (fade_to - fade_from)
                )
            )
            for x in range(
                fade_to
            )
        ]

        mask = Image.new(
            "L",
            (
                fade_to,
                height
            )
        )

        mask.putdata(
            mask_row * height
        )

        img.paste(
            blurred.crop(
                (
                    0,
                    0,
                    fade_to,
                    height
                )
            ),
            (0, 0),
            mask
        )

        img.save(
            image_path
        )

    def _build_page_prompt(
        self,
        project
    ):

        style = project.get(
            "style",
            "Technical / Modern"
        )

        topic = project.get(
            "topic",
            ""
        )

        return f"""
Create a professional educational full-page illustration for an infographic poster.

Theme:
{topic}

Visual style:
{style}

Composition requirements:

The illustration fills the entire portrait frame edge to edge.
Place the main subject and visual interest on the RIGHT and CENTER of the frame.
Keep the LEFT 45% of the frame as a completely empty calm area with only a smooth gradient or soft abstract texture.
Keep the TOP area smooth and uncluttered for a headline.
Use only abstract shapes, gradients, and soft edges throughout the artwork.

General requirements:

Clean professional illustration.
Modern editorial infographic artwork.
High visual clarity.
Cohesive color palette.
Strong composition with a natural reading flow from left to right.
The finished artwork should read as a well-designed poster background ready to receive an overlaid headline and body copy.
"""
