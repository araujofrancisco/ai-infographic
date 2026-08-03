import base64
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from models import InfographicContent


PAGE_WIDTH = 2489
PAGE_HEIGHT = 3508

MARGIN = 140

COLUMN_WIDTH = round(
    PAGE_WIDTH * 0.42
)

TEXT_PAD = 55

TEXT_SHADOW = "rgba(2, 6, 23, 0.45)"
SHADOW_OFFSET = 4

TITLE_FONT = 92
SUBTITLE_FONT = 42
TITLE_GAP = 124
SUBTITLE_GAP = 108

PAGE_SCRIM_TOP = "rgba(2, 6, 23, 0.26)"
PAGE_SCRIM_MID = "rgba(2, 6, 23, 0.10)"
PAGE_SCRIM_BOTTOM = "rgba(2, 6, 23, 0.36)"
TEXT_SCRIM_END = 0.66

CARD_TITLE_FONT = 48
TITLE_LINE_FACTOR = 1.28

DESCRIPTION_FONT = 31
DESCRIPTION_LINE_HEIGHT = 44
DESCRIPTION_GAP = 20
DESCRIPTION_OPACITY = 0.85

BULLET_FONT = 29
BULLET_LINE_HEIGHT = 42
BULLET_SPACING = 12
BULLET_GAP = 28
BULLET_TEXT = "#F8FAFC"
DOT_RADIUS = 6
DOT_GAP = 30

BLOCK_GAP = 42
DIVIDER_WIDTH_FRACTION = 0.55
DIVIDER_STROKE = "rgba(255, 255, 255, 0.22)"
DIVIDER_TILE = 14

MIN_SCALE = 0.6
SCALE_STEP = 0.05

FONT_FAMILY = "Liberation Sans, DejaVu Sans, sans-serif"

THEMES = [
    {
        "name": "Teal / Aqua",
        "accent": "#5EEAD4"
    },
    {
        "name": "Slate / Steel Blue",
        "accent": "#93C5FD"
    },
    {
        "name": "Deep Blue / Muted Orange",
        "accent": "#FDBA74"
    },
    {
        "name": "Terracotta / Warm Amber",
        "accent": "#FDE68A"
    }
]


@dataclass(frozen=True)
class Layout:

    title_font: int
    subtitle_font: int
    title_gap: int
    subtitle_gap: int

    text_pad: int

    card_title_font: int
    title_line_height: int

    description_font: int
    description_line_height: int
    description_gap: int

    bullet_font: int
    bullet_line_height: int
    bullet_spacing: int
    bullet_gap: int
    dot_radius: int
    dot_gap: int

    block_gap: int


@dataclass(frozen=True)
class _Block:

    index: int
    y: int
    height: int
    text_x: int
    text_width: int
    title_lines: list[str]
    description_lines: list[str]
    bullet_items: list["BulletItem"]


@dataclass(frozen=True)
class BulletItem:

    prefix: str | None
    rest: str
    lines: list[str]
    is_example: bool


def render_infographic(
    content: InfographicContent,
    image_paths: list[str],
    svg_path: Path,
    png_path: Path,
    pdf_path: Path
):

    svg_content = build_svg(
        content=content,
        image_paths=image_paths
    )

    import cairosvg

    svg_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    svg_path.write_text(
        svg_content,
        encoding="utf-8"
    )

    cairosvg.svg2png(
        bytestring=svg_content.encode(
            "utf-8"
        ),
        write_to=str(
            png_path
        ),
        output_width=PAGE_WIDTH,
        output_height=PAGE_HEIGHT
    )

    cairosvg.svg2pdf(
        bytestring=svg_content.encode(
            "utf-8"
        ),
        write_to=str(
            pdf_path
        )
    )


def build_svg(
    content: InfographicContent,
    image_paths: list[str],
    scale: float | None = None
) -> str:

    if scale is None:

        scale = _fit_scale(
            content=content,
            image_paths=image_paths
        )

    layout = _metrics(
        scale
    )

    blocks, _total = _plan_layout(
        sections=content.sections,
        layout=layout
    )

    svg = []

    svg.append(
        f"""
<svg
    xmlns="http://www.w3.org/2000/svg"
    width="{PAGE_WIDTH}"
    height="{PAGE_HEIGHT}"
    viewBox="0 0 {PAGE_WIDTH} {PAGE_HEIGHT}"
>
"""
    )

    svg.append(
        _defs()
    )

    svg.append(
        f"""
<rect
    x="0"
    y="0"
    width="{PAGE_WIDTH}"
    height="{PAGE_HEIGHT}"
    fill="#FFFFFF"
/>
"""
    )

    encoded = base64.b64encode(
        Path(
            image_paths[0]
        ).read_bytes()
    ).decode(
        "utf-8"
    )

    svg.append(
        f"""
<image
    x="0"
    y="0"
    width="{PAGE_WIDTH}"
    height="{PAGE_HEIGHT}"
    preserveAspectRatio="xMidYMid slice"
    href="data:image/png;base64,{encoded}"
/>
"""
    )

    svg.append(
        f"""
<rect
    x="0"
    y="0"
    width="{PAGE_WIDTH}"
    height="{PAGE_HEIGHT}"
    fill="url(#pageScrim)"
/>
"""
    )

    column_end = (
        MARGIN
        + COLUMN_WIDTH
    )

    svg.append(
        f"""
<rect
    x="0"
    y="0"
    width="{column_end + 260}"
    height="{PAGE_HEIGHT}"
    fill="url(#textScrim)"
/>
"""
    )

    text_x = (
        MARGIN
        + layout.text_pad
    )

    y = MARGIN

    svg.extend(
        _shadowed(
            text_x,
            y + layout.title_font,
            content.title,
            size=layout.title_font,
            weight="bold",
            color="#FFFFFF"
        )
    )

    y += layout.title_gap

    svg.extend(
        _shadowed(
            text_x,
            y + layout.subtitle_font,
            content.subtitle,
            size=layout.subtitle_font,
            weight="normal",
            color="#E8EDF5",
            opacity=0.9
        )
    )

    for index, block in enumerate(
        blocks
    ):

        theme = THEMES[
            index % len(THEMES)
        ]

        svg.extend(
            _block_text(
                block=block,
                layout=layout,
                theme=theme
            )
        )

    svg.append(
        "</svg>"
    )

    return "\n".join(
        svg
    )


def _defs() -> str:

    return """
<defs>
    <linearGradient id="pageScrim" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="PAGE_SCRIM_TOP"/>
        <stop offset="0.5" stop-color="PAGE_SCRIM_MID"/>
        <stop offset="1" stop-color="PAGE_SCRIM_BOTTOM"/>
    </linearGradient>
    <linearGradient id="textScrim" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="rgba(2, 6, 23, 0.66)"/>
        <stop offset="0.55" stop-color="rgba(2, 6, 23, 0.55)"/>
        <stop offset="1" stop-color="rgba(2, 6, 23, 0)"/>
    </linearGradient>
</defs>
""".replace(
        "PAGE_SCRIM_TOP",
        PAGE_SCRIM_TOP
    ).replace(
        "PAGE_SCRIM_MID",
        PAGE_SCRIM_MID
    ).replace(
        "PAGE_SCRIM_BOTTOM",
        PAGE_SCRIM_BOTTOM
    )


def _block_text(
    block: _Block,
    layout: Layout,
    theme: dict
) -> list[str]:

    elements = []

    cursor = block.y

    baseline = (
        cursor
        + layout.card_title_font
    )

    badge = f"{block.index + 1:02d}"

    for line_index, line in enumerate(
        block.title_lines
    ):

        if line_index == 0:

            elements.extend(
                _shadowed_header(
                    block.text_x,
                    baseline,
                    badge,
                    line,
                    layout.card_title_font,
                    theme["accent"]
                )
            )

        else:

            elements.extend(
                _shadowed(
                    block.text_x,
                    baseline,
                    line,
                    size=layout.card_title_font,
                    weight="bold",
                    color="#FFFFFF"
                )
            )

        baseline += layout.title_line_height

    cursor += (
        len(block.title_lines)
        * layout.title_line_height
    )

    cursor += layout.description_gap

    for line in block.description_lines:

        elements.extend(
            _shadowed(
                block.text_x,
                cursor + layout.description_font,
                line,
                size=layout.description_font,
                weight="normal",
                color="#E8EDF5",
                opacity=DESCRIPTION_OPACITY,
                font_style="italic"
            )
        )

        cursor += layout.description_line_height

    cursor += layout.bullet_gap

    for item in block.bullet_items:

        elements.extend(
            _bullet_block(
                block=block,
                layout=layout,
                item=item,
                top=cursor,
                theme=theme
            )
        )

        cursor += (
            len(item.lines)
            * layout.bullet_line_height
            + layout.bullet_spacing
        )

    divider_y = (
        block.y
        + block.height
    )

    elements.append(
        f"""
<line
    x1="{block.text_x}"
    y1="{divider_y}"
    x2="{block.text_x + round(block.text_width * DIVIDER_WIDTH_FRACTION)}"
    y2="{divider_y}"
    stroke="{DIVIDER_STROKE}"
    stroke-width="3"
/>
"""
    )

    tile_size = round(
        DIVIDER_TILE * (
            layout.title_line_height / CARD_TITLE_FONT
        )
    )

    elements.append(
        f"""
<rect
    x="{block.text_x}"
    y="{divider_y - tile_size}"
    width="{tile_size}"
    height="{tile_size}"
    rx="{round(tile_size * 0.3)}"
    fill="{theme['accent']}"
    opacity="0.9"
/>
"""
    )

    return elements


def _bullet_block(
    block: _Block,
    layout: Layout,
    item: BulletItem,
    top: int,
    theme: dict
) -> list[str]:

    elements = []

    bullet_x = (
        block.text_x
        + layout.dot_gap
    )

    baseline = (
        top
        + layout.bullet_font
    )

    elements.append(
        f"""
<circle
    cx="{block.text_x + layout.dot_radius}"
    cy="{baseline - layout.dot_radius}"
    r="{layout.dot_radius}"
    fill="{theme['accent']}"
    opacity="0.95"
/>
"""
        if not item.is_example
        else f"""
<rect
    x="{block.text_x - 2}"
    y="{top}"
    width="4"
    height="{len(item.lines) * layout.bullet_line_height}"
    rx="2"
    fill="{theme['accent']}"
    opacity="0.9"
/>
"""
    )

    for line_index, line in enumerate(
        item.lines
    ):

        if (
            line_index == 0
            and item.prefix
        ):

            remaining = line[
                len(item.prefix):
            ].lstrip()

            elements.extend(
                _shadowed_prefix(
                    x=bullet_x,
                    y=baseline,
                    prefix=item.prefix,
                    rest=remaining,
                    size=layout.bullet_font,
                    fill=BULLET_TEXT,
                    prefix_color=(
                        theme["accent"]
                        if item.is_example
                        else "#FFFFFF"
                    ),
                    font_style=(
                        "italic"
                        if item.is_example
                        else None
                    )
                )
            )

        else:

            elements.extend(
                _shadowed(
                    bullet_x,
                    baseline,
                    line,
                    size=layout.bullet_font,
                    weight="normal",
                    color=BULLET_TEXT,
                    font_style=(
                        "italic"
                        if item.is_example
                        else None
                    )
                )
            )

        baseline += layout.bullet_line_height

    return elements


def _bullet_prefix(
    bullet: str,
    is_example: bool
):

    if (
        is_example
        and "example" not in bullet.lower()
    ):

        return "Example:", bullet

    if ":" in bullet:

        head, _, tail = bullet.partition(
            ":"
        )

        return (
            head.strip() + ":",
            tail.strip()
        )

    return None, bullet


def _shadowed(
    x,
    y,
    text,
    size,
    weight,
    color,
    font_style=None,
    opacity=None
) -> list[str]:

    return [
        text_element(
            x + SHADOW_OFFSET,
            y + SHADOW_OFFSET,
            text,
            size=size,
            weight=weight,
            color=TEXT_SHADOW,
            font_style=font_style,
            opacity=0.45
        ),
        text_element(
            x,
            y,
            text,
            size=size,
            weight=weight,
            color=color,
            font_style=font_style,
            opacity=opacity
        )
    ]


def _shadowed_header(
    x,
    y,
    badge,
    title,
    size,
    accent
) -> list[str]:

    return [
        _header_text(
            x + SHADOW_OFFSET,
            y + SHADOW_OFFSET,
            badge,
            title,
            size,
            TEXT_SHADOW,
            opacity=0.45
        ),
        _header_text(
            x,
            y,
            badge,
            title,
            size,
            "#FFFFFF",
            accent=accent
        )
    ]


def _shadowed_prefix(
    x,
    y,
    prefix,
    rest,
    size,
    fill,
    prefix_color,
    font_style
) -> list[str]:

    return [
        _text_with_prefix(
            x + SHADOW_OFFSET,
            y + SHADOW_OFFSET,
            prefix,
            rest,
            size,
            TEXT_SHADOW,
            prefix_color=TEXT_SHADOW,
            font_style=font_style,
            opacity=0.45
        ),
        _text_with_prefix(
            x,
            y,
            prefix,
            rest,
            size,
            fill,
            prefix_color=prefix_color,
            font_style=font_style
        )
    ]


def _header_text(
    x,
    y,
    badge,
    title,
    size,
    fill,
    accent=None,
    opacity=None
):

    attributes = (
        f'x="{x}" '
        f'y="{y}" '
        f'font-family="{FONT_FAMILY}" '
        f'font-size="{size}px" '
        f'font-weight="bold" '
        f'fill="{fill}"'
    )

    if opacity is not None:

        attributes += (
            f' opacity="{opacity}"'
        )

    return f"""
<text {attributes}>
    <tspan fill="{accent or fill}">{escape(badge)}</tspan>
    <tspan>  {escape(title)}</tspan>
</text>
"""


def _text_with_prefix(
    x,
    y,
    prefix,
    rest,
    size,
    fill,
    prefix_color=None,
    font_style=None,
    opacity=None
):

    if rest:

        body = (
            f'<tspan font-weight="bold" fill="{prefix_color or fill}">{escape(prefix)}</tspan>'
            f'<tspan> {escape(rest)}</tspan>'
        )

    else:

        body = (
            f'<tspan font-weight="bold" fill="{prefix_color or fill}">{escape(prefix)}</tspan>'
        )

    attributes = (
        f'x="{x}" '
        f'y="{y}" '
        f'font-family="{FONT_FAMILY}" '
        f'font-size="{size}px" '
        f'font-weight="normal" '
        f'fill="{fill}"'
    )

    if font_style:

        attributes += (
            f' font-style="{font_style}"'
        )

    if opacity is not None:

        attributes += (
            f' opacity="{opacity}"'
        )

    return f"""
<text {attributes}>
    {body}
</text>
"""


def _fit_scale(
    content: InfographicContent,
    image_paths: list[str]
) -> float:

    limit = (
        PAGE_HEIGHT
        - MARGIN
    )

    scale = 1.0

    while scale >= MIN_SCALE:

        if (
            _layout_height(
                content=content,
                image_paths=image_paths,
                scale=scale
            )
            <= limit
        ):

            return scale

        scale = round(
            scale - SCALE_STEP,
            2
        )

    return MIN_SCALE


def _layout_height(
    content: InfographicContent,
    image_paths: list[str],
    scale: float
) -> int:

    layout = _metrics(
        scale
    )

    _blocks, total = _plan_layout(
        sections=content.sections,
        layout=layout
    )

    return total


def _plan_layout(
    sections,
    layout: Layout
):

    text_x = (
        MARGIN
        + layout.text_pad
    )

    text_width = (
        COLUMN_WIDTH
        - (2 * layout.text_pad)
    )

    bullet_text_width = (
        text_width
        - layout.dot_gap
    )

    blocks = []

    y = (
        MARGIN
        + layout.title_gap
        + layout.subtitle_gap
    )

    for index, section in enumerate(
        sections
    ):

        title_lines = _wrap(
            text=section.title,
            max_width=text_width,
            font_size=layout.card_title_font
        )

        description_lines = _wrap(
            text=section.short_description,
            max_width=text_width,
            font_size=layout.description_font
        )

        bullet_items = []

        for bindex, bullet in enumerate(
            section.bullet_points
        ):

            is_example = (
                bindex
                == len(section.bullet_points) - 1
            )

            prefix, rest = _bullet_prefix(
                bullet=bullet,
                is_example=is_example
            )

            full = (
                f"{prefix} {rest}"
                if prefix
                else rest
            )

            lines = _wrap(
                text=full,
                max_width=bullet_text_width,
                font_size=layout.bullet_font
            )

            bullet_items.append(
                BulletItem(
                    prefix=prefix,
                    rest=rest,
                    lines=lines,
                    is_example=is_example
                )
            )

        height = _block_height(
            title_lines=title_lines,
            description_lines=description_lines,
            bullet_items=bullet_items,
            layout=layout
        )

        blocks.append(
            _Block(
                index=index,
                y=y,
                height=height,
                text_x=text_x,
                text_width=text_width,
                title_lines=title_lines,
                description_lines=description_lines,
                bullet_items=bullet_items
            )
        )

        y += (
            height
            + layout.block_gap
        )

    return blocks, y


def _metrics(
    scale: float
) -> Layout:

    return Layout(
        title_font=round(
            TITLE_FONT * scale
        ),
        subtitle_font=round(
            SUBTITLE_FONT * scale
        ),
        title_gap=round(
            TITLE_GAP * scale
        ),
        subtitle_gap=round(
            SUBTITLE_GAP * scale
        ),
        text_pad=round(
            TEXT_PAD * scale
        ),
        card_title_font=round(
            CARD_TITLE_FONT * scale
        ),
        title_line_height=round(
            CARD_TITLE_FONT
            * TITLE_LINE_FACTOR
            * scale
        ),
        description_font=round(
            DESCRIPTION_FONT * scale
        ),
        description_line_height=round(
            DESCRIPTION_LINE_HEIGHT * scale
        ),
        description_gap=round(
            DESCRIPTION_GAP * scale
        ),
        bullet_font=round(
            BULLET_FONT * scale
        ),
        bullet_line_height=round(
            BULLET_LINE_HEIGHT * scale
        ),
        bullet_spacing=round(
            BULLET_SPACING * scale
        ),
        bullet_gap=round(
            BULLET_GAP * scale
        ),
        dot_radius=round(
            DOT_RADIUS * scale
        ),
        dot_gap=round(
            DOT_GAP * scale
        ),
        block_gap=round(
            BLOCK_GAP * scale
        )
    )


def _block_height(
    title_lines: list[str],
    description_lines: list[str],
    bullet_items: list[BulletItem],
    layout: Layout
) -> int:

    title_height = (
        len(title_lines)
        * layout.title_line_height
    )

    description_height = (
        len(description_lines)
        * layout.description_line_height
    )

    bullets_height = (
        sum(
            len(item.lines)
            * layout.bullet_line_height
            for item in bullet_items
        )
        + (
            (len(bullet_items) - 1)
            * layout.bullet_spacing
        )
    )

    return (
        title_height
        + layout.description_gap
        + description_height
        + layout.bullet_gap
        + bullets_height
    )


def text_element(
    x,
    y,
    text,
    size,
    weight,
    color,
    font_style=None,
    opacity=None
):

    attributes = (
        f'x="{x}" '
        f'y="{y}" '
        f'font-family="{FONT_FAMILY}" '
        f'font-size="{size}px" '
        f'font-weight="{weight}" '
        f'fill="{color}"'
    )

    if font_style:

        attributes += (
            f' font-style="{font_style}"'
        )

    if opacity is not None:

        attributes += (
            f' opacity="{opacity}"'
        )

    return f"""
<text {attributes}>
    {escape(text)}
</text>
"""


def _wrap(
    text: str,
    max_width: int,
    font_size: int
) -> list[str]:

    words = text.split()

    lines = []

    current = ""

    approximate_chars = int(
        max_width
        / (font_size * 0.55)
    )

    for word in words:

        test = (
            f"{current} {word}"
        ).strip()

        if len(test) > approximate_chars:

            lines.append(
                current
            )

            current = word

        else:

            current = test

    if current:

        lines.append(
            current
        )

    return lines
