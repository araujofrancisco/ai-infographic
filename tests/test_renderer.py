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


def test_build_svg_rejects_empty_image_paths():

    content = make_content(
        [
            make_section(
                index
            )
            for index in range(3)
        ]
    )

    try:

        renderer.build_svg(
            content=content,
            image_paths=[]
        )

    except ValueError:

        pass

    else:

        raise AssertionError(
            "build_svg should reject empty image paths"
        )


def test_cap_lines_truncates_with_ellipsis():

    capped = renderer._cap_lines(
        [
            "line one",
            "line two",
            "line three"
        ]
    )

    assert len(capped) == 2

    assert (
        renderer.ELLIPSIS
        in capped[1]
    )


def test_cap_lines_short_passes_through():

    lines = [
        "line one",
        "line two"
    ]

    assert (
        renderer._cap_lines(
            lines
        )
        == lines
    )


def test_plan_header_wraps_long_title():

    content = make_content(
        [
            make_section(
                index
            )
            for index in range(3)
        ]
    )

    content.title = (
        "A very long infographic title that absolutely must wrap "
        "across multiple lines instead of overflowing the column"
    )

    header = renderer._plan_header(
        content=content,
        layout=renderer._metrics(1.0)
    )

    assert len(
        header.title_lines
    ) == renderer.MAX_HEADER_LINES

    assert (
        renderer.ELLIPSIS
        in header.title_lines[-1]
    )

    assert (
        header.block_start
        > renderer.MARGIN
        + renderer._metrics(1.0).title_gap
        + renderer._metrics(1.0).subtitle_gap
    )


def test_build_svg_renders_wrapped_title():

    content = make_content(
        [
            make_section(
                index
            )
            for index in range(3)
        ]
    )

    content.title = (
        "A very long infographic title that absolutely must wrap "
        "across multiple lines instead of overflowing the column"
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
            renderer.ELLIPSIS
        ) >= 1


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
