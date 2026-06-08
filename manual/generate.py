"""
Generate a nanoblock-style PDF manual from a build-plan JSON.

Usage:
    python -m manual.generate manual/samples/house.json
    python -m manual.generate manual/samples/house.json -o house_manual.pdf

Layout (modelled on the reference booklets in ./references/):
  - a cover page with the finished model;
  - step pages laid out as a grid of cells, each cell = a boxed step number, a parts list
    of little iso block icons with x-counts, and the build-so-far diagram (new blocks
    hovering on drop-lines above pale already-built blocks);
  - a "Finished!" page with the full model.

Still iterating on the exact look — easy knobs are grouped at the top.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from . import buildplan, iso
except ImportError:
    import buildplan, iso


# --- Layout knobs ----------------------------------------------------------------
COLS, ROWS = 2, 2          # step cells per page
MARGIN = 40.0              # page margin
GUTTER = 14.0             # gap between cells
INK = (0.12, 0.12, 0.12)
GREY = (0.5, 0.5, 0.5)
HAIRLINE = (0.8, 0.8, 0.8)


def _require_reportlab():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        sys.exit("This needs ReportLab:\n    pip install -r manual/requirements.txt")


def render(plan, out_path: Path) -> int:
    from reportlab.lib.colors import Color
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas

    page_w, page_h = A4
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)

    steps = list(buildplan.iter_steps(plan))
    final = steps[-1].cumulative if steps else []

    _cover(c, plan, final, page_w, page_h, Color)
    c.showPage()

    per_page = COLS * ROWS
    for i in range(0, len(steps), per_page):
        _step_page(c, plan, steps[i:i + per_page], page_w, page_h, Color)
        c.showPage()

    _finished(c, plan, final, page_w, page_h, Color)
    c.showPage()

    c.save()
    return len(steps)


# --- Pages -----------------------------------------------------------------------

def _cover(c, plan, final, page_w, page_h, Color):
    c.setFillColor(Color(*INK))
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(page_w / 2, page_h - 120, plan.name)
    c.setFillColor(Color(*GREY))
    c.setFont("Helvetica", 13)
    c.drawCentredString(page_w / 2, page_h - 145, "SnapBlock build manual")

    iso.draw_diagram(c, (MARGIN, 150, page_w - MARGIN, page_h - 220), final, set(), plan.palette)

    c.setFillColor(Color(*GREY))
    c.setFont("Helvetica", 9)
    total = len(final)
    c.drawCentredString(page_w / 2, 110, f"{total} blocks  -  build it bottom-up, follow the steps")


def _finished(c, plan, final, page_w, page_h, Color):
    iso.draw_diagram(c, (MARGIN, 150, page_w - MARGIN, page_h - 200), final, set(), plan.palette)
    c.setFillColor(Color(*INK))
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(page_w / 2, page_h - 130, "Finished!")
    c.setFillColor(Color(*GREY))
    c.setFont("Helvetica-Oblique", 10)
    c.drawCentredString(page_w / 2, 120, "A few spare blocks are normal.")


def _step_page(c, plan, steps, page_w, page_h, Color):
    grid_w = page_w - 2 * MARGIN
    grid_h = page_h - 2 * MARGIN
    cell_w = (grid_w - (COLS - 1) * GUTTER) / COLS
    cell_h = (grid_h - (ROWS - 1) * GUTTER) / ROWS

    for idx, step in enumerate(steps):
        col = idx % COLS
        row = idx // COLS
        x0 = MARGIN + col * (cell_w + GUTTER)
        # rows fill top-to-bottom
        y1 = page_h - MARGIN - row * (cell_h + GUTTER)
        y0 = y1 - cell_h
        _step_cell(c, plan, step, (x0, y0, x0 + cell_w, y1), Color)


def _step_cell(c, plan, step, rect, Color):
    x0, y0, x1, y1 = rect

    # cell separator (hairline)
    c.setStrokeColor(Color(*HAIRLINE))
    c.setLineWidth(0.6)
    c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)

    pad = 8.0
    # boxed step number, top-left
    n = str(step.step_global)
    c.setFillColor(Color(*INK))
    c.setLineWidth(1.0)
    c.setStrokeColor(Color(*INK))
    box = 16.0
    bx, by = x0 + pad, y1 - pad - box
    c.rect(bx, by, box, box, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(bx + box / 2, by + box / 2 - 3.5, n)

    # bag label, next to the number
    c.setFillColor(Color(*GREY))
    c.setFont("Helvetica", 8)
    c.drawString(bx + box + 6, by + box / 2 - 3, step.bag_name)

    # parts list: a horizontal row under the header (icon + xN per distinct piece).
    parts_y = by - 12
    px = x0 + pad + 4
    icon_size = 0.36
    for part in step.parts:
        rgb = plan.palette[part.material]
        iw = iso.icon_width(part.width, part.depth, icon_size)
        iso.draw_part_icon(c, (px + iw / 2, parts_y), part.width, part.depth,
                           part.finish, rgb, icon_size)
        c.setFillColor(Color(*INK))
        c.setFont("Helvetica", 8)
        label = f"x{part.count}"
        tx = px + iw + 3
        c.drawString(tx, parts_y - 3, label)
        px = tx + c.stringWidth(label, "Helvetica", 8) + 12

    # diagram fills the rest of the cell, below the parts row
    diag = (x0 + pad, y0 + pad, x1 - pad, parts_y - 16)
    iso.draw_diagram(c, diag, step.cumulative, {b.cell for b in step.new}, plan.palette)


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
