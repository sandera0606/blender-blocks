"""
Generate a nanoblock-style PDF manual from a build-plan JSON.

Usage:
    python -m manual.generate manual/samples/house.json
    python -m manual.generate manual/samples/house.json -o house_manual.pdf

Layout (modelled on the reference booklets in ./references/), with a soft Blender Blocks
identity layered on top — warm cream paper, a slim rounded typeface, muted pastels, and
little sparkles:
  - a cover page: a wordmark, the model name, a hero diagram on a soft ground shadow, and
    a row of pastel info pills (blocks / steps / bags);
  - step pages: a rounded header band (model name + wordmark), then a grid of sticker
    cards. Each card has a pastel step bubble, a bag label, a tinted parts strip of little
    iso block icons with x-counts, and the build-so-far diagram (new blocks hovering on
    drop-lines above pale already-built blocks);
  - a "Finished!" page: a soft badge with sparkles, the full model on a ground shadow.

Easy knobs are grouped at the top. The Mulish fonts in ./assets/ are used when present
and fall back to Helvetica otherwise, so the tool still runs without them.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

try:
    from . import buildplan, iso
except ImportError:
    import buildplan, iso


# --- Layout knobs ----------------------------------------------------------------
COLS, ROWS = 2, 2          # step cards per page
MARGIN = 42.0              # page margin
GUTTER = 16.0              # gap between cards
BAND_H = 32.0              # header band height on step pages
FOOTER_Y = 30.0            # baseline of the footer text
RADIUS = 6.0              # the (gently, not bubbly) rounded corner radius

# --- Palette (calm warm-white paper + a single muted accent) ---------------------
PAPER = (0.969, 0.962, 0.951)   # soft warm white — fills every page
INK = (0.20, 0.19, 0.21)        # warm near-charcoal
MUTED = (0.55, 0.52, 0.53)
CARD = (1.0, 1.0, 1.0)
CARD_EDGE = (0.90, 0.88, 0.86)
TINT = (0.961, 0.954, 0.946)    # parts-strip wash (faint warm grey)
WHITE = (1.0, 1.0, 1.0)

ACCENT = (0.70, 0.45, 0.44)     # muted clay rose — the one restrained accent
ACCENT_SOFT = (0.82, 0.62, 0.60)

WORDMARK = "blender blocks"

# Fonts: filled in by _register_fonts(); Helvetica is the graceful fallback.
F_DISPLAY = "Helvetica-Bold"
F_BODY = "Helvetica"
_ASSETS = Path(__file__).resolve().parent / "assets"


def _require_reportlab():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        sys.exit("This needs ReportLab:\n    pip install -r manual/requirements.txt")


def _register_fonts():
    """Register the bundled Quicksand weights if they're present. Returns silently and
    leaves the Helvetica fallback in place if the asset files aren't there."""
    global F_DISPLAY, F_BODY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pairs = [("Mulish-Display", "Mulish-Display.ttf"),
             ("Mulish-Body", "Mulish-Body.ttf")]
    out = []
    for name, fname in pairs:
        path = _ASSETS / fname
        try:
            if path.exists():
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                out.append(name)
            else:
                out.append(None)
        except Exception:
            out.append(None)
    F_DISPLAY = out[0] or "Helvetica-Bold"
    F_BODY = out[1] or "Helvetica"


# --- Colour helpers --------------------------------------------------------------

def _mix(rgb, target, t):
    return tuple(a + (b - a) * t for a, b in zip(rgb, target))


def _lighten(rgb, t=0.80):
    return _mix(rgb, (1.0, 1.0, 1.0), t)


def _darken(rgb, t=0.40):
    return _mix(rgb, (0.0, 0.0, 0.0), t)


def _fill(c, Color, rgb):
    c.setFillColor(Color(*rgb))


# --- Small drawing helpers -------------------------------------------------------

def _tracked_width(c, text, font, size, track):
    return c.stringWidth(text, font, size) + track * (len(text) - 1)


def _draw_tracked(c, Color, x, y, text, font, size, color, track, *, center=False):
    """Draw text with letter-spacing. Char-spacing is a text-state parameter that persists
    in the PDF graphics state, so we bracket it in save/restore to keep it from bleeding
    into later plain strings; centre by hand off the tracked width."""
    if center:
        x -= _tracked_width(c, text, font, size, track) / 2.0
    c.saveState()
    to = c.beginText(x, y)
    to.setFont(font, size)
    to.setFillColor(Color(*color))
    to.setCharSpace(track)
    to.textOut(text)
    c.drawText(to)
    c.restoreState()


def _wordmark(c, Color, x, y, *, size=11, color=ACCENT, track=2.8, center=False, right=False):
    if right:
        x -= _tracked_width(c, WORDMARK, F_DISPLAY, size, track)
    _draw_tracked(c, Color, x, y, WORDMARK, F_DISPLAY, size, color, track, center=center)


def _soft_shadow(c, Color, x, y, w, h, r, *, dx=0.0, dy=-2.5, alpha=0.10):
    """A soft offset shadow behind a rounded shape, for a paper-sticker feel."""
    c.saveState()
    c.setFillColor(Color(0.55, 0.50, 0.50))
    c.setFillAlpha(alpha)
    c.setStrokeAlpha(0.0)
    c.roundRect(x + dx, y + dy, w, h, r, stroke=0, fill=1)
    c.restoreState()


def _page_bg(c, Color, page_w, page_h):
    c.setFillColor(Color(*PAPER))
    c.rect(0, 0, page_w, page_h, stroke=0, fill=1)


def _pills(c, Color, cx, y, items, *, size=10, h=22.0, gap=10.0, padx=14.0):
    """A centred row of quiet, uniform tags (gently rounded, not stadium), e.g.
    ['18 blocks', '4 steps', '2 bags']."""
    c.setFont(F_BODY, size)
    widths = [c.stringWidth(t, F_BODY, size) + 2 * padx for t in items]
    total = sum(widths) + gap * (len(items) - 1)
    x = cx - total / 2.0
    for text, w in zip(items, widths):
        _fill(c, Color, WHITE)
        c.setStrokeColor(Color(*_lighten(ACCENT, 0.50)))
        c.setLineWidth(1.0)
        c.roundRect(x, y - h / 2, w, h, RADIUS, stroke=1, fill=1)
        _fill(c, Color, INK)
        c.drawCentredString(x + w / 2, y - size / 2 + 1.5, text)
        x += w + gap


def _footer(c, Color, page_w, page_label):
    c.setStrokeColor(Color(*CARD_EDGE))
    c.setLineWidth(0.7)
    c.line(MARGIN, FOOTER_Y + 13, page_w - MARGIN, FOOTER_Y + 13)
    _wordmark(c, Color, MARGIN, FOOTER_Y, size=9, color=MUTED, track=2.2)
    if page_label:
        _fill(c, Color, MUTED)
        c.setFont(F_BODY, 9)
        c.drawRightString(page_w - MARGIN, FOOTER_Y, page_label)


# --- Pages -----------------------------------------------------------------------

def _cover(c, plan, final, counts, page_w, page_h, Color):
    _page_bg(c, Color, page_w, page_h)
    cx = page_w / 2.0
    n_blocks, n_steps, n_bags = counts

    _wordmark(c, Color, cx, page_h - 94, size=11, color=ACCENT, track=4.2, center=True)

    _fill(c, Color, INK)
    c.setFont(F_DISPLAY, 37)
    c.drawCentredString(cx, page_h - 152, plan.name)
    _draw_tracked(c, Color, cx, page_h - 176, "BUILD MANUAL", F_BODY, 9.5, MUTED, 3.2, center=True)

    iso.draw_diagram(c, (MARGIN, 168, page_w - MARGIN, page_h - 212), final, set(),
                     plan.palette, ground_shadow=True)

    _pills(c, Color, cx, 128, [f"{n_blocks} blocks", f"{n_steps} steps", f"{n_bags} bags"])
    _fill(c, Color, MUTED)
    c.setFont(F_BODY, 10)
    c.drawCentredString(cx, 96, "Build from the bottom up, following the steps in order.")


def _finished(c, plan, final, counts, page_w, page_h, Color):
    _page_bg(c, Color, page_w, page_h)
    cx = page_w / 2.0
    n_blocks, n_steps, _ = counts

    _wordmark(c, Color, cx, page_h - 88, size=11, color=ACCENT, track=4.0, center=True)

    # a quiet badge, no fanfare
    label = "Finished"
    track = 1.2
    inner = _tracked_width(c, label, F_DISPLAY, 18, track)
    bw, bh = inner + 50, 36
    bx, by = cx - bw / 2.0, page_h - 152
    badge_r = 9.0
    _soft_shadow(c, Color, bx, by, bw, bh, badge_r, dy=-2.5, alpha=0.10)
    _fill(c, Color, ACCENT)
    c.roundRect(bx, by, bw, bh, badge_r, stroke=0, fill=1)
    _draw_tracked(c, Color, cx, by + bh / 2 - 6.0, label, F_DISPLAY, 18, WHITE, track, center=True)

    iso.draw_diagram(c, (MARGIN, 150, page_w - MARGIN, page_h - 192), final, set(),
                     plan.palette, ground_shadow=True)

    _fill(c, Color, MUTED)
    c.setFont(F_BODY, 11)
    c.drawCentredString(cx, 122, "A few spare blocks are normal.")
    _pills(c, Color, cx, 94, [f"{n_blocks} blocks", f"{n_steps} steps"])


def _band(c, Color, page_w, page_h, title):
    """The soft header band on step pages. Returns its bottom y."""
    x = MARGIN
    w = page_w - 2 * MARGIN
    y = page_h - MARGIN - BAND_H
    _soft_shadow(c, Color, x, y, w, BAND_H, RADIUS, dy=-2.0, alpha=0.09)
    _fill(c, Color, ACCENT)
    c.roundRect(x, y, w, BAND_H, RADIUS, stroke=0, fill=1)

    _fill(c, Color, WHITE)
    c.setFont(F_DISPLAY, 13.5)
    c.drawString(x + 16, y + BAND_H / 2 - 5, title)
    _wordmark(c, Color, x + w - 16, y + BAND_H / 2 - 3.5, size=9.5,
              color=_lighten(ACCENT, 0.55), track=2.6, right=True)
    return y


def _step_page(c, plan, steps, page_w, page_h, Color, page_label):
    _page_bg(c, Color, page_w, page_h)
    band_bottom = _band(c, Color, page_w, page_h, plan.name)

    top = band_bottom - 18
    bottom = FOOTER_Y + 28
    grid_w = page_w - 2 * MARGIN
    grid_h = top - bottom
    cell_w = (grid_w - (COLS - 1) * GUTTER) / COLS
    cell_h = (grid_h - (ROWS - 1) * GUTTER) / ROWS

    for idx, step in enumerate(steps):
        col = idx % COLS
        row = idx // COLS
        x0 = MARGIN + col * (cell_w + GUTTER)
        y1 = top - row * (cell_h + GUTTER)
        y0 = y1 - cell_h
        _step_cell(c, plan, step, (x0, y0, x0 + cell_w, y1), Color)

    _footer(c, Color, page_w, page_label)


def _step_cell(c, plan, step, rect, Color):
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0

    # soft sticker card
    _soft_shadow(c, Color, x0, y0, w, h, RADIUS, dy=-2.5, alpha=0.09)
    _fill(c, Color, CARD)
    c.setStrokeColor(Color(*CARD_EDGE))
    c.setLineWidth(0.9)
    c.roundRect(x0, y0, w, h, RADIUS, stroke=1, fill=1)

    pad = 13.0
    bub = 21.0
    bx, by = x0 + pad, y1 - pad - bub

    # step badge (rounded square) — pale accent fill, accent ring, ink numeral
    _fill(c, Color, _lighten(ACCENT, 0.84))
    c.setStrokeColor(Color(*ACCENT))
    c.setLineWidth(1.2)
    c.roundRect(bx, by, bub, bub, 5, stroke=1, fill=1)
    _fill(c, Color, _darken(ACCENT, 0.30))
    c.setFont(F_DISPLAY, 12)
    c.drawCentredString(bx + bub / 2, by + bub / 2 - 4.0, str(step.step_global))

    # bag label, beside the badge
    _draw_tracked(c, Color, bx + bub + 9, by + bub / 2 - 3.0,
                  step.bag_name.upper(), F_BODY, 8.0, MUTED, 0.9)

    # parts strip: a tinted band of icon + xN per distinct piece
    strip_h = 27.0
    strip_y = by - 10 - strip_h
    _fill(c, Color, TINT)
    c.roundRect(x0 + pad, strip_y, w - 2 * pad, strip_h, RADIUS, stroke=0, fill=1)

    px = x0 + pad + 12
    cy = strip_y + strip_h / 2.0
    icon_size = 0.34
    for part in step.parts:
        rgb = plan.palette[part.material]
        iw = iso.icon_width(part.width, part.depth, icon_size)
        iso.draw_part_icon(c, (px + iw / 2, cy + 1.5), part.width, part.depth,
                           part.finish, rgb, icon_size)
        _fill(c, Color, INK)
        c.setFont(F_BODY, 9)
        label = f"×{part.count}"
        tx = px + iw + 3
        c.drawString(tx, cy - 3.2, label)
        px = tx + c.stringWidth(label, F_BODY, 9) + 14

    # diagram fills the rest of the card, below the parts strip
    diag = (x0 + pad, y0 + pad, x1 - pad, strip_y - 10)
    iso.draw_diagram(c, diag, step.cumulative, {b.cell for b in step.new}, plan.palette)


def render(plan, out_path: Path) -> int:
    from reportlab.lib.colors import Color
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas

    _register_fonts()

    page_w, page_h = A4
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)

    steps = list(buildplan.iter_steps(plan))
    final = steps[-1].cumulative if steps else []
    counts = (len(final), len(steps), len(plan.bags))

    _cover(c, plan, final, counts, page_w, page_h, Color)
    c.showPage()

    per_page = COLS * ROWS
    total_pages = max(1, math.ceil(len(steps) / per_page))
    for page_i, i in enumerate(range(0, len(steps), per_page), start=1):
        _step_page(c, plan, steps[i:i + per_page], page_w, page_h, Color,
                   f"{page_i} / {total_pages}")
        c.showPage()

    _finished(c, plan, final, counts, page_w, page_h, Color)
    c.showPage()

    c.save()
    return len(steps)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a nanoblock-style PDF manual from a build plan.")
    parser.add_argument("plan", help="path to a build-plan JSON (see docs/build_plan.md)")
    parser.add_argument("-o", "--out", help="output PDF path (default: <plan>_manual.pdf)")
    args = parser.parse_args(argv)

    _require_reportlab()

    plan_path = Path(args.plan)
    out_path = Path(args.out) if args.out else plan_path.with_name(plan_path.stem + "_manual.pdf")

    plan = buildplan.load_plan(plan_path)
    pages = render(plan, out_path)
    print(f"Wrote {out_path}  ({pages} steps, '{plan.name}')")


if __name__ == "__main__":
    main()
