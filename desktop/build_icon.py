"""Build `desktop/assets/aegis.ico` from the app logo.

    python -m desktop.build_icon

`frontend/public/logo.png` is the white A-and-arrow on a TRANSPARENT background.
Shipped bare as an icon it disappears against a light wallpaper, a light
taskbar, or Explorer's white list background -- so it is composited onto a dark
rounded tile at every size. The logo itself stays white, which is the one thing
that was asked for.

Windows picks the nearest size from a multi-image .ico; a single 256px image
gets downsampled to 16px by the shell and turns to mush, so all seven standard
sizes are rendered independently.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "frontend" / "public" / "logo.png"
OUT_ICO = REPO / "desktop" / "assets" / "aegis.ico"
OUT_PNG = REPO / "desktop" / "assets" / "aegis_256.png"

SIZES = (16, 24, 32, 48, 64, 128, 256)
#: the app's own dark ground (matches the splash in `aegis_desktop.py`)
TILE = (13, 17, 23, 255)
CORNER = 0.18          # radius as a fraction of the side
PAD = 0.13             # breathing room as a fraction of the side


def tile(src, n: int):
    from PIL import Image, ImageDraw

    bg = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(bg).rounded_rectangle(
        [0, 0, n - 1, n - 1], radius=max(2, round(n * CORNER)), fill=TILE)
    pad = round(n * PAD)
    bg.alpha_composite(src.resize((n - 2 * pad, n - 2 * pad), Image.LANCZOS), (pad, pad))
    return bg


def main() -> int:
    from PIL import Image

    if not SRC.exists():
        print(f"REFUSED: no logo at {SRC}", file=sys.stderr)
        return 1
    src = Image.open(SRC).convert("RGBA")
    imgs = [tile(src, n) for n in SIZES]
    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    imgs[-1].save(OUT_ICO, format="ICO", sizes=[(n, n) for n in SIZES],
                  append_images=imgs[:-1])
    imgs[-1].save(OUT_PNG)
    print(f"wrote {OUT_ICO} ({OUT_ICO.stat().st_size:,} bytes) at sizes {list(SIZES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
