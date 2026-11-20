"""Draw Channel 92's era logos: the channel's mark as it looked in the 1950s to the 1990s, as PNGs with alpha.

    python tools/make_era_logos.py [--out src/atomic_flix/brand/eras] [--fonts DIR]

Needs Pillow (the optional extra: pip install -e ".[brand]"); the kit itself never imports it, and the PNGs it
writes ship in the package. Every letter is set in a real font found on this machine (the font files used are
printed); nothing is drawn by a model. The words are always CHANNEL and 92, exactly. The 2000s wear the channel's
own modern mark (assets/channel92-logo.png: black leaning letters on a cream slip with a pink stroke), so this
script does not draw them; the older eras are older looks of the same channel:

    1950s  an engraved serif on a light card with a double rule, the 92 hatched like an engraving
    1960s  heavy sans in cream on a charcoal plate over a strip of teal, red and mustard blocks
    1970s  rounded heavy letters in cream with stacked brown, orange and amber outlines
    1980s  a chrome 92 with a dark outline, CHANNEL in neon pink with its glow, both leaning
    1990s  white letters with cyan and magenta copies split apart and a few slices knocked sideways
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
except ImportError:  # the kit runs without Pillow; only this tool needs it
    sys.exit("make_era_logos needs Pillow: pip install -e \".[brand]\"")

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "src" / "atomic_flix" / "brand" / "eras"
FONT_ROLES = {
    "serif": ["georgiab.ttf", "Georgia Bold.ttf", "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf", "timesbd.ttf"],
    "heavy": ["ariblk.ttf", "Arial Black.ttf", "impact.ttf", "FiraSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "bold": ["verdanab.ttf", "Verdana Bold.ttf", "FiraSans-Bold.ttf", "Roboto-Bold.ttf", "DejaVuSans-Bold.ttf"],
}
FONT_DIRS = [Path(os.environ.get("WINDIR", "/nowhere")) / "Fonts",
             Path(os.environ.get("LOCALAPPDATA", "/nowhere")) / "Microsoft" / "Windows" / "Fonts",
             Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path("~/.fonts").expanduser(),
             Path("/Library/Fonts"), Path("~/Library/Fonts").expanduser()]
CREAM, INK = (244, 234, 213, 255), (17, 17, 17, 255)


def find_font(role: str, extra: list[Path]) -> Path:
    for folder in [*extra, *FONT_DIRS]:
        for name in FONT_ROLES[role]:
            hits = list(folder.rglob(name)) if folder.is_dir() else []
            if hits:
                return hits[0]
    sys.exit(f"no {role} font found (tried {', '.join(FONT_ROLES[role])}); pass --fonts DIR")


def text_mask(text: str, font: Path, size: int, spacing: int = 0, pad: int = 40) -> Image.Image:
    """A greyscale mask of TEXT set in FONT at SIZE, SPACING pixels between letters, PAD of room left around it."""
    face = ImageFont.truetype(str(font), size)
    widths = [face.getbbox(ch)[2] for ch in text]
    canvas = Image.new("L", (sum(widths) + spacing * len(text) + 2 * pad, size * 2 + 2 * pad), 0)
    draw, x = ImageDraw.Draw(canvas), pad
    for ch, width in zip(text, widths):
        draw.text((x, pad), ch, font=face, fill=255)
        x += width + spacing
    left, top, right, bottom = canvas.getbbox()
    return canvas.crop((left - pad, top - pad, right + pad, bottom + pad))


def shear(image: Image.Image, lean: float) -> Image.Image:
    """IMAGE leaning right by LEAN (horizontal shift per pixel of height), widened to keep every pixel."""
    extra = int(abs(lean) * image.height) + 2
    return image.transform((image.width + extra, image.height), Image.AFFINE, (1, lean, -extra if lean > 0 else 0,
                                                                                0, 1, 0), Image.BICUBIC)


def grow(mask: Image.Image, pixels: int) -> Image.Image:
    """MASK grown by PIXELS with rounded corners (a blur, then a threshold)."""
    blurred = mask.filter(ImageFilter.GaussianBlur(pixels / 2)) if pixels else mask
    return blurred.point(lambda v: 255 if v > (40 if pixels else 127) else 0)


def rounded(mask: Image.Image, radius: int) -> Image.Image:
    """MASK with its corners rounded: blurred and cut back at the middle grey."""
    return mask.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: 255 if v > 127 else 0)


def solid(size: tuple[int, int], colour) -> Image.Image:
    return Image.new("RGBA", size, colour)


def paste_mask(canvas: Image.Image, colour, mask: Image.Image, at: tuple[int, int]) -> None:
    canvas.paste(solid(mask.size, colour), at, mask)


def gradient(size: tuple[int, int], stops: list[tuple[float, tuple[int, int, int]]]) -> Image.Image:
    """A vertical gradient through STOPS (share of the height, RGB)."""
    width, height = size
    column = Image.new("RGBA", (1, height))
    for y in range(height):
        share = y / max(1, height - 1)
        (a, ca), (b, cb) = next((s, t) for s, t in zip(stops, stops[1:]) if s[0] <= share <= t[0])
        k = (share - a) / max(1e-6, b - a)
        column.putpixel((0, y), tuple(int(ca[i] + (cb[i] - ca[i]) * k) for i in range(3)) + (255,))
    return column.resize((width, height))


def fifties(fonts: dict[str, Path]) -> Image.Image:
    word = text_mask("CHANNEL", fonts["serif"], 104, spacing=26)
    number = text_mask("92", fonts["serif"], 400)
    width = max(word.width, number.width) + 220
    height = word.height + number.height + 190
    logo = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    plate = ImageDraw.Draw(logo)
    plate.rounded_rectangle((4, 4, width - 5, height - 5), 36, fill=(232, 232, 228, 255), outline=INK, width=8)
    plate.rounded_rectangle((26, 26, width - 27, height - 27), 22, outline=INK, width=3)
    top = 62
    paste_mask(logo, INK, word, ((width - word.width) // 2, top))
    rule_y = top + word.height + 34
    plate.line((70, rule_y, width - 70, rule_y), fill=INK, width=3)
    hatch = Image.new("L", number.size, 0)
    lines = ImageDraw.Draw(hatch)
    for y in range(0, number.height, 9):
        lines.rectangle((0, y, number.width, y + 4), fill=255)
    at = ((width - number.width) // 2, rule_y + 30)
    paste_mask(logo, INK, ImageChops.subtract(grow(number, 10), number), (at[0], at[1]))
    paste_mask(logo, INK, ImageChops.multiply(number, hatch), at)
    return logo


SIXTIES_PLATE = (30, 29, 28, 255)     # near-neutral charcoal: a colour delay has almost no colour here to move
SIXTIES_STRIP = ((0.44, (31, 122, 140, 255)), (0.34, (209, 70, 47, 255)), (0.22, (224, 165, 38, 255)))


def sixties(fonts: dict[str, Path]) -> Image.Image:
    """Cream letters on a charcoal plate, read by light against dark; the colour is a strip of teal, red and mustard
    blocks below the plate, in rows of its own, so the 1960s look's long colour delay smears it sideways (a little
    past the plate's right edge) and never across a letter. Colour blocks behind the letters slid off them ("922")."""
    word = text_mask("CHANNEL", fonts["heavy"], 130, spacing=24, pad=0)
    number = text_mask("92", fonts["heavy"], 420, spacing=10, pad=0)
    side, top, gap, strip_gap, strip = 70, 60, 40, 50, 100
    width = max(word.width, number.width) + 2 * side
    plate_h = top + word.height + gap + number.height + strip_gap
    logo = Image.new("RGBA", (width, plate_h + strip), (0, 0, 0, 0))
    draw = ImageDraw.Draw(logo)
    draw.rectangle((0, 0, width - 1, plate_h - 1), fill=SIXTIES_PLATE)
    x = 0
    for i, (share, colour) in enumerate(SIXTIES_STRIP):
        right = width if i == len(SIXTIES_STRIP) - 1 else x + round(width * share)
        draw.rectangle((x, plate_h, right - 1, plate_h + strip - 1), fill=colour)
        x = right
    paste_mask(logo, CREAM, word, ((width - word.width) // 2, top))
    paste_mask(logo, CREAM, number, ((width - number.width) // 2, top + word.height + gap))
    return logo


def stacked(word: Image.Image, number: Image.Image, gap: int, pad: int) -> Image.Image:
    """WORD centred over NUMBER, GAP apart, PAD around both, as one mask."""
    width = max(word.width, number.width) + 2 * pad
    mask = Image.new("L", (width, word.height + gap + number.height + 2 * pad), 0)
    mask.paste(word, ((width - word.width) // 2, pad))
    mask.paste(number, ((width - number.width) // 2, pad + word.height + gap))
    return mask


def seventies(fonts: dict[str, Path]) -> Image.Image:
    word = rounded(text_mask("CHANNEL", fonts["heavy"], 170, spacing=4, pad=0), 6)
    number = rounded(text_mask("92", fonts["heavy"], 380, pad=0), 10)
    base = stacked(word, number, 40, 70)
    canvas = Image.new("L", (base.width, base.height + 40), 0)
    canvas.paste(base, (0, 0))
    logo = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    for grown, drop, colour in ((40, 30, (90, 52, 24, 255)), (28, 20, (232, 112, 42, 255)),
                                (16, 10, (242, 163, 58, 255)), (6, 0, (90, 52, 24, 255))):
        paste_mask(logo, colour, grow(canvas, grown), (0, drop))
    paste_mask(logo, (247, 227, 192, 255), canvas, (0, 0))
    return logo.crop(logo.getbbox())


def eighties(fonts: dict[str, Path]) -> Image.Image:
    word = shear(text_mask("CHANNEL", fonts["heavy"], 130, spacing=10), 0.22)
    number = shear(text_mask("92", fonts["heavy"], 420), 0.22)
    width = max(word.width, number.width) + 140
    height = word.height + number.height + 120
    logo = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    word_at = ((width - word.width) // 2 + 40, 40)
    outline = ImageChops.subtract(grow(word, 6), word)
    glow = grow(word, 6).filter(ImageFilter.GaussianBlur(12))
    paste_mask(logo, (255, 46, 160, 170), glow, word_at)
    paste_mask(logo, (255, 80, 190, 255), outline, word_at)
    paste_mask(logo, (255, 225, 246, 255), ImageChops.subtract(word, grow(word, 0).filter(ImageFilter.MinFilter(9))),
               word_at)
    number_at = ((width - number.width) // 2 - 20, word.height + 70)
    paste_mask(logo, (20, 16, 48, 255), grow(number, 14), number_at)
    chrome = gradient(number.size, [(0.0, (236, 248, 255)), (0.45, (104, 160, 214)), (0.52, (26, 24, 60)),
                                    (0.62, (210, 150, 90)), (1.0, (255, 241, 214))])
    logo.paste(chrome, number_at, number)
    return logo.crop(logo.getbbox())


def nineties(fonts: dict[str, Path]) -> Image.Image:
    word = text_mask("CHANNEL", fonts["bold"], 150, spacing=2, pad=12)
    number = text_mask("92", fonts["bold"], 400, pad=12)
    letters = shear(stacked(word, number, 20, 0), 0.1)
    pad, split = 60, 14
    logo = Image.new("RGBA", (letters.width + 2 * pad, letters.height + 2 * pad), (0, 0, 0, 0))
    paste_mask(logo, (0, 230, 255, 255), letters, (pad - split, pad))
    paste_mask(logo, (255, 0, 200, 255), letters, (pad + split, pad))
    paste_mask(logo, INK, grow(letters, 8), (pad, pad))
    paste_mask(logo, (255, 255, 255, 255), letters, (pad, pad))
    for top, high, push in ((0.14, 0.05, 34), (0.5, 0.04, -26), (0.78, 0.03, 18)):
        y0, y1 = int(logo.height * top), int(logo.height * (top + high))
        strip = logo.crop((0, y0, logo.width, y1))
        logo.paste((0, 0, 0, 0), (0, y0, logo.width, y1))
        logo.paste(strip, (push, y0))
    return logo.crop(logo.getbbox())


DRAWN = {"1950s": fifties, "1960s": sixties, "1970s": seventies, "1980s": eighties, "1990s": nineties}
MAX_WIDTH = 1200


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--fonts", type=Path, action="append", default=[], help="another folder to look for fonts in")
    args = p.parse_args(argv)
    fonts = {role: find_font(role, args.fonts) for role in FONT_ROLES}
    for role, path in fonts.items():
        print(f"{role} font: {path.name}")
    args.out.mkdir(parents=True, exist_ok=True)
    for era_id, draw in DRAWN.items():
        logo = draw(fonts)
        if logo.width > MAX_WIDTH:
            logo = logo.resize((MAX_WIDTH, round(logo.height * MAX_WIDTH / logo.width)), Image.LANCZOS)
        out = args.out / f"logo-{era_id}.png"
        logo.save(out, optimize=True)
        print(f"wrote {out} ({logo.width}x{logo.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
