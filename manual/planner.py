"""
The deterministic planner: voxel model -> build plan.

Given a voxel model (filled coloured cells), produce a build plan (see
../docs/build_plan.md) by:

  1. deciding stud vs smooth per exposed-top cell (heuristic + per-material override),
  2. merging cells into rectangular blocks (capped greedy, per layer, per material+class),
     with seams staggered between layers so it reads as hand-laid,
  3. ordering bottom-up so nothing is placed in mid-air,
  4. chunking into steps and bags.

Pure standard library + the local catalogue. Fully deterministic: same input ->
byte-identical output (no dict-ordering or RNG dependence).
"""

from __future__ import annotations

from collections import defaultdict, deque

from . import catalogue

# --- Tunable knobs ---------------------------------------------------------------
SMOOTH_MIN_REGION = 6     # an exposed-top flat region >= this many cells reads as smooth
MERGE_MAX_DIM = catalogue.MERGE_MAX_DIM
STEP_MAX = 4              # blocks per step
BAG_LAYERS = 2           # z-layers per bag


class _Placed:
    __slots__ = ("ox", "oy", "z", "w", "d", "material", "finish", "studs")

    def __init__(self, ox, oy, z, w, d, material, finish, studs):
        self.ox, self.oy, self.z = ox, oy, z
        self.w, self.d = w, d
        self.material, self.finish, self.studs = material, finish, studs


def _connected_components(xy_set):
    """4-connected components of a set of (x, y) cells, each returned as a sorted list."""
    seen = set()
    comps = []
    for start in sorted(xy_set):
        if start in seen:
            continue
        comp = []
        q = deque([start])
        seen.add(start)
        while q:
            x, y = q.popleft()
            comp.append((x, y))
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) in xy_set and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    q.append((nx, ny))
        comps.append(sorted(comp))
    return comps


def _classify(filled, overrides):
    """Return class_of[(x,y,z)] in {'stud','smooth'} for every filled cell.

    Exposed-top cells: 'smooth' if in a large flat region (or overridden), else 'stud'.
    Covered cells: 'stud' (body) so they merge with studded neighbours, not smooth tiles.
    """
    exposed = {(x, y, z) for (x, y, z) in filled if (x, y, z + 1) not in filled}

    by_layer = defaultdict(set)
    for (x, y, z) in exposed:
        by_layer[z].add((x, y))

    smooth_cells = set()
    for z, xy in by_layer.items():
        for comp in _connected_components(xy):
            if len(comp) >= SMOOTH_MIN_REGION:
                smooth_cells.update((x, y, z) for (x, y) in comp)

    class_of = {}
    for cell in filled:
        material = filled[cell]
        ov = overrides.get(material)
        if cell in exposed and ov in ("smooth", "studded"):
            class_of[cell] = "smooth" if ov == "smooth" else "stud"
        elif cell in smooth_cells:
            class_of[cell] = "smooth"
        else:
            class_of[cell] = "stud"
    return class_of, exposed


def _greedy_cover(group_xy, direction):
    """Cover a set of same-group (x,y) cells with catalogue rectangles.

    `direction` (+1 or -1) is the x growth/scan direction; alternating it per layer
    staggers seams between layers. Deterministic given the inputs. Returns a list of
    (origin_x, origin_y, w, d) with origin at the min -X/-Y corner.
    """
    uncovered = set(group_xy)
    # Anchor scan order: rows front-to-back; within a row, leading edge first for this
    # direction (left->right when +1, right->left when -1).
    anchors = sorted(group_xy, key=lambda xy: (xy[1], direction * xy[0]))
    out = []
    for (ax, ay) in anchors:
        if (ax, ay) not in uncovered:
            continue
        for (w, d) in catalogue.merge_candidates(MERGE_MAX_DIM):
            cells = [(ax + direction * i, ay + j) for i in range(w) for j in range(d)]
            if all(cmp in uncovered for cmp in cells):
                for cmp in cells:
                    uncovered.discard(cmp)
                ox = min(ax, ax + direction * (w - 1))
                out.append((ox, ay, w, d))
                break
    return out


def plan(voxel: dict, overrides: dict | None = None) -> dict:
    overrides = dict(overrides or {})
    overrides.update(voxel.get("overrides") or {})

    filled = {tuple(c["cell"]): c["material"] for c in voxel.get("cells", [])}
    class_of, exposed = _classify(filled, overrides)

    # --- merge per layer, per (material, class) ---
    placed: list[_Placed] = []
    layers = sorted({z for (_, _, z) in filled})
    for z in layers:
        groups = defaultdict(set)
        for (x, y, cz) in filled:
            if cz == z:
                groups[(filled[(x, y, z)], class_of[(x, y, z)])].add((x, y))
        direction = 1 if z % 2 == 0 else -1
        for (material, cls), xy in sorted(groups.items()):
            for (ox, oy, w, d) in _greedy_cover(xy, direction):
                studs = []
                if cls == "stud":
                    studs = [[ox + i, oy + j]
                             for i in range(w) for j in range(d)
                             if (ox + i, oy + j, z) in exposed]
                else:
                    # INVARIANT: you can't attach a block onto a studless tile, so a
                    # smooth block must have NOTHING directly above it. Guaranteed because
                    # 'smooth' is only ever assigned to exposed-top cells (see _classify);
                    # asserted here so a future change to the rules can't silently break it.
                    assert all((ox + i, oy + j, z + 1) not in filled
                               for i in range(w) for j in range(d)), \
                        "smooth block has a filled cell directly above it"
                placed.append(_Placed(ox, oy, z, w, d, material, cls, studs))

    # --- order bottom-up, deterministic within a layer ---
    placed.sort(key=lambda b: (b.z, b.oy, b.ox))

    # --- chunk into steps (within a layer) then bags (bands of layers) ---
    bags_by_band = defaultdict(list)   # band index -> list of steps (each a list of block dicts)
    i = 0
    while i < len(placed):
        z = placed[i].z
        group = []
        while i < len(placed) and placed[i].z == z and len(group) < STEP_MAX:
            b = placed[i]
            block = {
                "cell": [b.ox, b.oy, b.z],
                "type": f"{b.w}x{b.d}",   # as-placed WxD so the renderer spans correctly
                "material": b.material,
                "finish": "stud" if b.finish == "stud" else "smooth",
            }
            if b.finish == "stud":
                block["studs"] = b.studs
            group.append(block)
            i += 1
        bags_by_band[z // BAG_LAYERS].append({"add": group})

    bags = []
    for band in sorted(bags_by_band):
        bags.append({"name": f"Bag {band + 1}", "steps": bags_by_band[band]})

    return {
        "version": 1,
        "model": {"name": voxel.get("name", "Untitled")},
        "grid": voxel.get("grid", {"U": 1.0, "H": 1.0}),
        "palette": voxel.get("palette", {}),
        "bags": bags,
    }


def main(argv=None):
    import argparse
    import json
    from pathlib import Path

    from . import vox_import

    parser = argparse.ArgumentParser(description="Plan a build (voxel model -> build plan JSON).")
    parser.add_argument("voxel", help="voxel model (.vox or voxel JSON)")
    parser.add_argument("-o", "--out", help="output build-plan JSON (default: <voxel>_plan.json)")
    parser.add_argument("--overrides", help="optional sidecar JSON of colour renames / finishes")
    args = parser.parse_args(argv)

    voxel = vox_import.load_voxel(args.voxel, args.overrides)
    build_plan = plan(voxel)
    out = Path(args.out) if args.out else Path(args.voxel).with_name(Path(args.voxel).stem + "_plan.json")
    out.write_text(json.dumps(build_plan, indent=2), encoding="utf-8")
    n = sum(len(s["add"]) for bag in build_plan["bags"] for s in bag["steps"])
    print(f"Wrote {out}  ({len(build_plan['bags'])} bags, {n} blocks)")


if __name__ == "__main__":
    main()
