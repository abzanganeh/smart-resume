#!/usr/bin/env python3
"""Generate Flint AI umbrella marketing images for LinkedIn."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FLINT_ASSETS = ROOT / "Flint" / "src" / "assets"
OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "marketing"

NAVY = (36, 52, 71)  # #243447
NAVY_LIGHT = (51, 65, 85)
ORANGE = (232, 148, 74)  # #E8944A
GOLD = (244, 185, 66)  # #F4B942
SLATE_950 = (15, 23, 42)
SLATE_900 = (30, 41, 59)
SLATE_400 = (148, 163, 184)
SLATE_300 = (203, 213, 225)
WHITE = (255, 255, 255)
AMBER = (251, 191, 36)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    if bold:
        path = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
    else:
        path = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"
    return ImageFont.truetype(path, size)


def load_logo(path: Path, height: int) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    ratio = height / img.height
    width = int(img.width * ratio)
    return img.resize((width, height), Image.Resampling.LANCZOS)


def draw_umbrella_arc(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    radius: int,
    width: int = 6,
) -> None:
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(bbox, start=200, end=-20, fill=GOLD, width=width)
    draw.arc(bbox, start=200, end=-20, fill=ORANGE, width=max(2, width // 2))


def draw_umbrella_handle(draw: ImageDraw.ImageDraw, cx: int, top: int, bottom: int) -> None:
    draw.line((cx, top, cx, bottom), fill=NAVY_LIGHT, width=5)


def paste_centered(base: Image.Image, overlay: Image.Image, x: int, y: int) -> None:
    ox = x - overlay.width // 2
    oy = y - overlay.height // 2
    base.paste(overlay, (ox, oy), overlay)


def rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int] | None = None,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=1 if outline else 0)


def generate_linkedin_umbrella() -> Path:
    w, h = 1200, 1200
    img = Image.new("RGB", (w, h), SLATE_950)
    draw = ImageDraw.Draw(img)

    for y in range(h):
        t = y / h
        r = int(SLATE_950[0] + (SLATE_900[0] - SLATE_950[0]) * t)
        g = int(SLATE_950[1] + (SLATE_900[1] - SLATE_950[1]) * t)
        b = int(SLATE_950[2] + (SLATE_900[2] - SLATE_950[2]) * t)
        draw.line((0, y, w, y), fill=(r, g, b))

    title_font = load_font(72, bold=True)
    subtitle_font = load_font(28)
    card_title_font = load_font(26, bold=True)
    card_body_font = load_font(20)
    badge_font = load_font(22, bold=True)
    launch_font = load_font(24, bold=True)

    cv_icon = load_logo(FLINT_ASSETS / "flint-logo-extension.png", 100)
    paste_centered(img, cv_icon, w // 2, 130)

    draw.text((w // 2, 210), "Flint AI", font=title_font, fill=WHITE, anchor="mm")
    draw.text(
        (w // 2, 265),
        "AI-powered tools for work",
        font=subtitle_font,
        fill=SLATE_400,
        anchor="mm",
    )

    umbrella_cy = 360
    draw_umbrella_arc(draw, w // 2, umbrella_cy, 420, width=8)
    draw_umbrella_handle(draw, w // 2, umbrella_cy + 20, 430)

    products = [
        {
            "logo": FLINT_ASSETS / "flint-logo-desktop.png",
            "logo_h": 72,
            "name": "TalioCV",
            "lines": ["AI resume tailoring", "Company intel & track"],
            "x": 200,
        },
        {
            "logo": FLINT_ASSETS / "flint-logo-extension.png",
            "logo_h": 72,
            "name": "Extension",
            "lines": ["Capture any JD", "One-click save"],
            "x": w // 2,
        },
        {
            "logo": FLINT_ASSETS / "flint-logo.png",
            "logo_h": 72,
            "name": "Meeting Copilot",
            "lines": ["Meeting prep", "Coaching & context"],
            "x": w - 200,
        },
    ]

    card_top = 470
    card_w, card_h = 320, 280
    for p in products:
        cx = p["x"]
        left = cx - card_w // 2
        top = card_top
        right = left + card_w
        bottom = top + card_h

        rounded_rect(draw, (left, top, right, bottom), 20, (30, 41, 59), outline=(51, 65, 85))

        logo = load_logo(p["logo"], p["logo_h"])
        paste_centered(img, logo, cx, top + 70)

        draw.text((cx, top + 130), p["name"], font=card_title_font, fill=WHITE, anchor="mm")
        y_line = top + 175
        for line in p["lines"]:
            draw.text((cx, y_line), line, font=card_body_font, fill=SLATE_400, anchor="mm")
            y_line += 32

        draw.line((cx, top + 28, w // 2, umbrella_cy + 18), fill=(51, 65, 85), width=2)

    badge_w, badge_h = 360, 52
    badge_x = w // 2 - badge_w // 2
    badge_y = 820
    rounded_rect(draw, (badge_x, badge_y, badge_x + badge_w, badge_y + badge_h), 26, ORANGE)
    draw.text(
        (w // 2, badge_y + badge_h // 2),
        "Launching July 2026",
        font=badge_font,
        fill=WHITE,
        anchor="mm",
    )

    draw.text(
        (w // 2, 920),
        "Web app  ·  Browser extension  ·  Desktop copilot",
        font=subtitle_font,
        fill=SLATE_300,
        anchor="mm",
    )
    draw.text(
        (w // 2, 965),
        "BYOK · Evidence-based · Never fabricates metrics",
        font=load_font(22),
        fill=SLATE_400,
        anchor="mm",
    )

    out = OUT_DIR / "flint-ai-umbrella-linkedin.png"
    img.save(out, "PNG", optimize=True)
    return out


def generate_poster_white() -> Path:
    """White poster content — matches framed mockup style for print/office use."""
    w, h = 1200, 1200
    img = Image.new("RGB", (w, h), WHITE)
    draw = ImageDraw.Draw(img)

    title_font = load_font(80, bold=True)
    subtitle_font = load_font(30)
    card_title_font = load_font(28, bold=True)
    card_body_font = load_font(22)
    tag_font = load_font(20)
    launch_font = load_font(26, bold=True)

    cv_icon = load_logo(FLINT_ASSETS / "flint-logo-extension.png", 140)
    paste_centered(img, cv_icon, w // 2, 160)

    draw.text((w // 2, 260), "Flint AI", font=title_font, fill=NAVY, anchor="mm")
    draw.text(
        (w // 2, 320),
        "YOUR ENTIRE JOB SEARCH, POWERED BY AI AGENTS",
        font=tag_font,
        fill=SLATE_400,
        anchor="mm",
    )

    draw_umbrella_arc(draw, w // 2, 400, 400, width=7)
    draw_umbrella_handle(draw, w // 2, 420, 470)

    products = [
        ("TalioCV", "Tailor · Intel · Track", FLINT_ASSETS / "flint-logo-desktop.png", 72, 200),
        ("Extension", "Any JD · One click", FLINT_ASSETS / "flint-logo-extension.png", 80, w // 2),
        ("Meeting Copilot", "Prep · Rehearsal", FLINT_ASSETS / "flint-logo.png", 80, w - 200),
    ]

    card_top = 510
    card_w, card_h = 300, 240
    for name, desc, logo_path, logo_h, cx in products:
        left = cx - card_w // 2
        top = card_top
        rounded_rect(draw, (left, top, left + card_w, top + card_h), 16, (248, 250, 252), outline=(226, 232, 240))
        logo = load_logo(logo_path, logo_h)
        paste_centered(img, logo, cx, top + 75)
        draw.text((cx, top + 145), name, font=card_title_font, fill=NAVY, anchor="mm")
        draw.text((cx, top + 185), desc, font=card_body_font, fill=SLATE_400, anchor="mm")
        draw.line((cx, top + 20, w // 2, 418), fill=(226, 232, 240), width=2)

    draw.text(
        (w // 2, 820),
        "Launching July 2026",
        font=launch_font,
        fill=ORANGE,
        anchor="mm",
    )
    draw.text(
        (w // 2, 870),
        "flint.app",
        font=subtitle_font,
        fill=NAVY,
        anchor="mm",
    )

    out = OUT_DIR / "flint-ai-umbrella-poster.png"
    img.save(out, "PNG", optimize=True)
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    linkedin_path = generate_linkedin_umbrella()
    poster_path = generate_poster_white()
    Image.open(linkedin_path).convert("RGB").save(
        OUT_DIR / "flint-ai-umbrella-linkedin.jpg", "JPEG", quality=92
    )
    Image.open(poster_path).convert("RGB").save(
        OUT_DIR / "flint-ai-umbrella-poster.jpg", "JPEG", quality=92
    )
    print(f"Wrote {linkedin_path}")
    print(f"Wrote {poster_path}")
    print(f"Wrote {OUT_DIR / 'flint-ai-umbrella-linkedin.jpg'}")
    print(f"Wrote {OUT_DIR / 'flint-ai-umbrella-poster.jpg'}")


if __name__ == "__main__":
    main()
