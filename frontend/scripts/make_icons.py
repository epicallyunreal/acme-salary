"""Writes ACME's icons into frontend/public/ from one drawing (D80).

From the repository root: uv run --with pillow python frontend/scripts/make_icons.py

A rounded square in the theme's primary with a white "A" drawn as a path, so it needs no font:
favicon.svg as the drawing itself, favicon.ico at 32 px and apple-touch-icon.png at 180 px drawn
from the same points. Pillow is a tool of this script alone, never a project dependency.
"""

from pathlib import Path

from PIL import Image, ImageDraw

PUBLIC = Path(__file__).resolve().parents[1] / "public"
PRIMARY = "#2F4A7A"  # tokens.primary in src/lib/theme.ts
SIZE = 64  # the drawing's own units
RADIUS = 14
# The A's outline, clockwise from the top left, and the counter inside it.
OUTER = [(27, 12), (37, 12), (51, 52), (42, 52), (39, 43), (25, 43), (22, 52), (13, 52)]
COUNTER = [(32, 22), (36.6, 35), (27.4, 35)]


def path(points) -> str:
    head, *rest = points
    return f"M{head[0]} {head[1]}" + "".join(f"L{x} {y}" for x, y in rest) + "Z"


def svg() -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">'
        f'<rect width="{SIZE}" height="{SIZE}" rx="{RADIUS}" fill="{PRIMARY}"/>'
        f'<path fill="#FFFFFF" fill-rule="evenodd" d="{path(OUTER)}{path(COUNTER)}"/>'
        "</svg>\n"
    )


def raster(pixels: int) -> Image.Image:
    """The same drawing at `pixels` square, drawn eight times larger and scaled down so its
    edges are smooth."""
    big = pixels * 8
    scale = big / SIZE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=RADIUS * scale, fill=PRIMARY)
    draw.polygon([(x * scale, y * scale) for x, y in OUTER], fill="#FFFFFF")
    draw.polygon([(x * scale, y * scale) for x, y in COUNTER], fill=PRIMARY)
    return image.resize((pixels, pixels), Image.Resampling.LANCZOS)


def main() -> None:
    PUBLIC.mkdir(exist_ok=True)
    (PUBLIC / "favicon.svg").write_text(svg())
    raster(32).save(PUBLIC / "favicon.ico", sizes=[(32, 32)])
    # The home screen draws its own rounded corners, so the touch icon is square and opaque.
    touch = Image.new("RGB", (180, 180), PRIMARY)
    icon = raster(180)
    touch.paste(icon, mask=icon)
    touch.save(PUBLIC / "apple-touch-icon.png")
    for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        print(name, (PUBLIC / name).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
