"""
Generate a nanoblock-style PDF manual from a build-plan JSON.

Usage:
    python -m manual.generate manual/samples/house.json
    python -m manual.generate manual/samples/house.json -o house_manual.pdf

One page per step: a header (model / bag / step counter), the isometric diagram of the
build up to that step (with the step's new blocks highlighted), and the step's parts list.

This is a FIRST-PASS layout. The look — page design, cover, typography, iso style — is
meant to be redesigned against the reference booklets in ./references/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Works both as `python -m manual.generate` (relative) and `python manual/generate.py`
# (the script's own dir is on sys.path, so the plain imports resolve).
try:
    from . import buildplan, iso
except ImportError:
    import buildplan, iso


def _require_reportlab():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        sys.exit(
            "This needs ReportLab. Install it with:\n"
            "    pip install -r manual/requirements.txt\n"
            "(or: pip install reportlab)"
        )


# --- First-pass page layout knobs (TODO: redesign against references) -------------
PAGE_MARGIN = 48.0
HEADER_GAP = 28.0


def render(plan, out_path: Path) -> int:
    from reportlab.lib.colors import Color
    from reportlab.lib.pagesizes import A5
    from reportlab.pdfgen import canvas as rl_canvas

    page_w, page_h = A5
    c = rl_canvas.Canvas(str(out_path), pagesize=A5)

    pages = 0
    for step in buildplan.iter_steps(plan):
        _draw_page(c, plan, step, page_w, page_h, Color)
        c.showPage()
        pages += 1

    if pages == 0:
        # An empty plan still produces a valid (empty) PDF rather than crashing.
        c.showPage()
    c.save()
    return pages


def _draw_page(c, plan, step, page_w, page_h, Color):
    # --- Header ---------------------------------------------------------------
    c.setFillColor(Color(0.1, 0.1, 0.1))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(PAGE_MARGIN, page_h - PAGE_MARGIN, plan.name)

    c.setFont("Helvetica", 10)
    c.setFillColor(Color(0.45, 0.45, 0.45))
    c.drawString(PAGE_MARGIN, page_h - PAGE_MARGIN - 16,
                 f"Bag {step.bag_index + 1}: {step.bag_name}")
    c.drawRightString(page_w - PAGE_MARGIN, page_h - PAGE_MARGIN,
                      f"Step {step.step_global} / {step.total_steps}")

    # --- Diagram --------------------------------------------------------------
    # Centre the cumulative diagram in the area between header and parts list.
    area_top = page_h - PAGE_MARGIN - HEADER_GAP - 16
    area_bottom = PAGE_MARGIN + 90  # leave room for the parts list
    area_cx = page_w / 2.0

    min_x, min_y, max_x, max_y = iso.diagram_bounds(step.cumulative)
    diag_cx = (min_x + max_x) / 2.0
    # In y-down math space, the page origin maps so the diagram centres in the area.
    ox = area_cx - diag_cx
    oy = (area_top + area_bottom) / 2.0 + (min_y + max_y) / 2.0

    new_cells = {b.cell for b in step.new}
    for b in iso.painter_order(step.cumulative):
        rgb = plan.palette[b.material]
        iso.draw_block(c, b, rgb, (ox, oy), highlight=b.cell in new_cells)

    # --- Parts list -----------------------------------------------------------
    c.setFillColor(Color(0.1, 0.1, 0.1))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(PAGE_MARGIN, PAGE_MARGIN + 60, "This step:")

    c.setFont("Helvetica", 10)
    c.setFillColor(Color(0.2, 0.2, 0.2))
    if step.parts:
        line = "    ".join(f"{p.count}x  {p.material} {p.type}" for p in step.parts)
    else:
        line = "(nothing — placeholder step)"
    c.drawString(PAGE_MARGIN, PAGE_MARGIN + 44, line)


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
    print(f"Wrote {out_path}  ({pages} page{'s' if pages != 1 else ''}, '{plan.name}')")


if __name__ == "__main__":
    main()
