"""
The rectangular block catalogue, for the planner and renderer.

DUPLICATED ON PURPOSE: the source of truth is `snapblock/constants.py:BLOCK_TYPES`,
but `manual/` can't import it (that package imports `bpy`, which only exists inside
Blender). So we keep the rectangular subset here, in sync by hand. Non-rectangular
blocks (round / smooth / step / L / T) are intentionally excluded — the merger only
covers with axis-aligned rectangles.
"""

from __future__ import annotations

import re

# id -> (W, D) canonical, with W >= D. Mirrors the rectangular entries of BLOCK_TYPES.
RECT_BLOCKS = {
    "1x1": (1, 1),
    "2x1": (2, 1),
    "2x2": (2, 2),
    "3x1": (3, 1),
    "3x2": (3, 2),
    "4x1": (4, 1),
    "4x2": (4, 2),
    "6x1": (6, 1),
    "8x2": (8, 2),
    "10x2": (10, 2),
    "10x4": (10, 4),
    "10x8": (10, 8),
    "10x10": (10, 10),
    "20x10": (20, 10),
    "20x20": (20, 20),
}

# Cap for the "varied / capped" merge vibe: drop the big 10x / 20x slabs so a build
# reads as many satisfying pieces rather than a few giant plates.
MERGE_MAX_DIM = 8

_TYPE_RE = re.compile(r"^(\d+)x(\d+)$")


def parse_dims(type_id: str) -> tuple[int, int]:
    """'4x2' -> (4, 2). Raises ValueError on a non-rectangular id."""
    m = _TYPE_RE.match(type_id)
    if not m:
        raise ValueError(f"not a rectangular block type: {type_id!r}")
    return int(m.group(1)), int(m.group(2))


def normalize_id(w: int, d: int) -> str:
    """Canonical library id for a placed W x D footprint (orientation-independent).
    A 1x4 placement uses the '4x1' library block rotated, so both count as one part."""
    return f"{max(w, d)}x{min(w, d)}"


def merge_candidates(max_dim: int = MERGE_MAX_DIM):
    """Placements (w, d) the merger may use, both orientations, largest-first.

    Deterministic order: largest area, then most-square, then wider-in-X. The merger
    walks this list and takes the first rectangle that fits, so the order *is* the
    tie-break policy."""
    cands = set()
    for (W, D) in RECT_BLOCKS.values():
        if max(W, D) > max_dim:
            continue
        cands.add((W, D))
        cands.add((D, W))
    return sorted(cands, key=lambda wd: (-(wd[0] * wd[1]), abs(wd[0] - wd[1]), -wd[0]))
