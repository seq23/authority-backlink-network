#!/usr/bin/env python3
"""Write each publication's icon set and social card from its own palette.

On 10 Oct 2026 /favicon.ico answered 404 on all three publications and no page
had an og:image, so every shared link rendered as a bare URL and every browser
that asks for /favicon.ico (most of them, before reading the <link>) logged a
miss. This writes, into each publication root:

  favicon.ico            16/32/48, the same mark as the site's favicon.svg
  apple-touch-icon.png   180x180, opaque (iOS composites transparency on black)
  icon-192.png, icon-512.png  for site.webmanifest
  site.webmanifest       name, colours and icons
  og.png                 1200x630 social card: the mark, the name, the first
                         sentence of the homepage definition and the domain, on the publication's own palette

Colours come from the publication's styles.css through lib.head_seo.palette(),
the same reader the head installer uses for theme-color. Each mark below is a
raster copy of that publication's favicon.svg -- three separate identities,
nothing shared. The files are committed; the build has no network or font
dependency at deploy time. Re-run after a palette or name change:

    python3 scripts/build_brand_assets.py --write

scripts/validators/validate_favicon_manifest.py checks the files exist at the
right sizes and that every page links them.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import head_seo as hs  # noqa: E402

SS = 16  # supersampling factor for the 32-unit favicon grid

FONT_CANDIDATES = {
    "serif-bold": ["/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"],
    "serif-bold-italic": ["/System/Library/Fonts/Supplemental/Georgia Bold Italic.ttf",
                          "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf"],
    "sans-bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "sans": ["/System/Library/Fonts/Supplemental/Arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}


def font(kind: str, size: int):
    for path in FONT_CANDIDATES[kind]:
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit(f"no {kind} font found; tried {FONT_CANDIDATES[kind]}")


def s(v: float) -> int:
    return round(v * SS)


# Each mark mirrors sites/<folder>/favicon.svg on a 32-unit grid.
def mark_founder(d: ImageDraw.ImageDraw, pal: dict) -> None:
    d.rounded_rectangle([0, 0, s(32) - 1, s(32) - 1], radius=s(3), fill="#0f1720")
    blue, w = "#3b82f6", 1.5  # stroke-width 3, square caps
    for x0, x1, xv in ((8, 12, 8), (20, 24, 24)):
        d.rectangle([s(x0 - w), s(8 - w), s(x1 + w), s(8 + w)], fill=blue)
        d.rectangle([s(x0 - w), s(24 - w), s(x1 + w), s(24 + w)], fill=blue)
        d.rectangle([s(xv - w), s(8 - w), s(xv + w), s(24 + w)], fill=blue)
    d.rectangle([s(14.5), s(14.5), s(17.5), s(17.5)], fill="#e8edf4")


def mark_memphis(d: ImageDraw.ImageDraw, pal: dict) -> None:
    d.ellipse([0, 0, s(32) - 1, s(32) - 1], fill="#fdfaf4")
    d.ellipse([s(1) - s(1), s(1) - s(1), s(31) + s(1) - 1, s(31) + s(1) - 1], fill="#a33f24")
    d.ellipse([s(2), s(2), s(30) - 1, s(30) - 1], fill="#fdfaf4")
    f = font("serif-bold-italic", s(19))
    d.text((s(16), s(23)), "M", font=f, fill="#a33f24", anchor="ms")


def mark_professional(d: ImageDraw.ImageDraw, pal: dict) -> None:
    navy = "#1c3f6e"
    d.rectangle([0, 0, s(32) - 1, s(32) - 1], fill="#ffffff")
    d.rectangle([0, 0, s(7) - 1, s(32) - 1], fill=navy)
    for y, w in ((7, 16), (14, 16), (21, 10)):
        d.rectangle([s(12), s(y), s(12 + w) - 1, s(y + 3) - 1], fill=navy)


MARKS = {"founder": mark_founder, "memphis": mark_memphis, "professional": mark_professional}
DISPLAY_FONT = {"founder": "sans-bold", "memphis": "serif-bold", "professional": "sans-bold"}


def mark(pid: str, pal: dict, size: int, opaque_bg: str | None = None) -> Image.Image:
    big = Image.new("RGBA", (s(32), s(32)), (0, 0, 0, 0))
    MARKS[pid](ImageDraw.Draw(big), pal)
    img = big.resize((size, size), Image.LANCZOS)
    if opaque_bg:
        bg = Image.new("RGBA", img.size, opaque_bg)
        bg.alpha_composite(img)
        img = bg.convert("RGB")
    return img


def wrap(text: str, f, width: int, draw: ImageDraw.ImageDraw, max_lines: int) -> list:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=f) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return lines


def card_line(pub: dict) -> str:
    """The first sentence of the homepage definition, without the name.

    The same answer the homepage gives under its H1, so the card and the page
    say one thing. 'X is a local publication for...' -> 'A local publication for...'.
    """
    first = pub["definition"].split(". ")[0].rstrip(".") + "."
    lead = pub["title"] + " is "
    if first.startswith(lead):
        first = first[len(lead):]
    return first[:1].upper() + first[1:]


def og_card(pub: dict, pal: dict) -> Image.Image:
    pid, W, H = pub["id"], hs.OG_WIDTH, hs.OG_HEIGHT
    img = Image.new("RGB", (W, H), pal["--bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 23, H], fill=pal["--accent"])
    img.paste(mark(pid, pal, 120, opaque_bg=pal["--bg"]), (96, 86))
    size = 76  # the name always sits on one line; shrink to fit
    while d.textlength(pub["title"], font=font(DISPLAY_FONT[pid], size)) > W - 192 and size > 48:
        size -= 2
    d.text((96, 250), pub["title"], font=font(DISPLAY_FONT[pid], size), fill=pal["--ink-strong"])
    y = 250 + size + 34
    body_f = font("sans", 32)
    for line in wrap(card_line(pub), body_f, W - 192, d, 3):
        d.text((96, y), line, font=body_f, fill=pal["--ink-muted"])
        y += 44
    d.text((96, H - 70), pub["working_domain"], font=font("sans-bold", 30),
           fill=pal["--accent"], anchor="ls")
    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build(pub: dict) -> dict:
    folder = ROOT / pub["folder"]
    pal = hs.palette((folder / "styles.css").read_text(encoding="utf-8"))
    pid = pub["id"]
    out: dict = {}
    ico = io.BytesIO()
    mark(pid, pal, 256).save(ico, format="ICO", sizes=[(n, n) for n in hs.ICO_SIZES])
    out[hs.FAVICON_ICO] = ico.getvalue()
    out[hs.APPLE_TOUCH_ICON] = png_bytes(mark(pid, pal, hs.APPLE_TOUCH_SIZE, opaque_bg=pal["--bg"]))
    for name, size in hs.MANIFEST_ICONS:
        out[name] = png_bytes(mark(pid, pal, size, opaque_bg=pal["--bg"]))
    out[hs.OG_IMAGE] = png_bytes(og_card(pub, pal))
    manifest = {
        "name": pub["title"], "short_name": pub["title"].split()[0],
        "description": pub["mission"], "start_url": "/", "scope": "/",
        "display": "browser", "background_color": pal["--bg"], "theme_color": pal["--accent"],
        "icons": [{"src": f"/{n}", "sizes": f"{z}x{z}", "type": "image/png"} for n, z in hs.MANIFEST_ICONS],
    }
    out[hs.MANIFEST] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    return out


def main() -> int:
    write = "--write" in sys.argv
    pubs = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    written = []
    for pub in pubs:
        if pub["id"] not in MARKS:
            raise SystemExit(f"no mark defined for publication '{pub['id']}' -- add one mirroring its favicon.svg")
        for name, data in build(pub).items():
            path = ROOT / pub["folder"] / name
            if write:
                path.write_bytes(data)
            written.append(str(path.relative_to(ROOT)))
    print(json.dumps({"mode": "write" if write else "check", "files": len(written)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
