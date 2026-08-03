import base64
import tempfile
from pathlib import Path
from types import SimpleNamespace

import renderer

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGNUSLjD"
    "gA0wYRUdtBIAE4MBbE0AHosAAAAASUVORK5CYII="
)


def make_section(
    index
):

    return SimpleNamespace(
        title=f"Section {index}",
        short_description=(
            "This section explains the core concept in a concise "
            "but complete way for the reader."
        ),
        bullet_points=[
            "Explains the fundamental idea behind the topic",
            "Shows a concrete example of how it is used",
            "Lists the main benefit for the reader",
            "Notes a common pitfall to avoid"
        ]
    )


def make_paths(
    base: Path,
    count: int
) -> list[str]:

    paths = []

    for index in range(
        count
    ):

        image = (
            base
            / f"section-{index + 1}.png"
        )

        image.write_bytes(
            TINY_PNG
        )

        paths.append(
            str(
                image
            )
        )

    return paths


def make_content(
    sections
):

    return SimpleNamespace(
        title="Test",
        subtitle="Sub",
        sections=sections
    )


def test_wrap_empty():

    assert renderer._wrap(
        "",
        100,
        30
    ) == []


def test_wrap_multiple_lines():

    wrapped = renderer._wrap(
        "word " * 100,
        max_width=400,
        font_size=30
    )

    assert len(wrapped) > 1

    assert all(
        line
        for line in wrapped
    )


def test_wrap_short_text_is_single_line():

    assert renderer._wrap(
        "hello",
        max_width=400,
        font_size=30
    ) == [
        "hello"
    ]


def test_fit_scale_light_is_full():

    light = make_content(
        [
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

    with tempfile.TemporaryDirectory() as tmp:

        paths = make_paths(
            Path(tmp),
            1
        )

        assert renderer._fit_scale(
            light,
            paths
        ) == 1.0


def test_fit_scale_dense_shrinks_within_page():

    dense = make_content(
        [
            make_section(
                index
            )
            for index in range(8)
        ]
    )

    with tempfile.TemporaryDirectory() as tmp:

        paths = make_paths(
            Path(tmp),
            8
        )

        fit = renderer._fit_scale(
            dense,
            paths
        )

        assert (
            renderer.MIN_SCALE
            <= fit
            < 1.0
        )

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
        )


def test_build_svg_is_poster_single_image():

    content = make_content(
        [
            SimpleNamespace(
                title="Section One",
                short_description=(
                    "A short description that is long enough to wrap "
                    "across several lines and needs measuring."
                ),
                bullet_points=[
                    "First bullet point that also wraps to two lines",
                    "Second bullet",
                    "Third bullet"
                ]
            )
        ]
    )

    with tempfile.TemporaryDirectory() as tmp:

        paths = make_paths(
            Path(tmp),
            1
        )

        svg = renderer.build_svg(
            content=content,
            image_paths=paths
        )

        assert svg.count(
            "<image"
        ) == 1

        assert "pageScrim" in svg

        assert "textScrim" in svg

        assert (
            f'height="{renderer.PAGE_HEIGHT}"'
            in svg
        )

        assert (
            f'width="{renderer.PAGE_WIDTH}"'
            in svg
        )
