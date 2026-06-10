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
STEP_MAX = 4              # blocks per step
BAG_LAYERS = 2           # z-layers per bag

# Piece sizing is a RATIO of the region, not a flat cap: a piece may span at most this
# fraction of a region's longer side, so a region is covered by roughly a constant
# *number* of pieces whatever its scale (small details -> small pieces; a big base ->
# big slabs). MERGE_MIN_CAP is a floor so tiny regions still allow a useful piece; the
# ceiling is whatever the catalogue offers (catalogue.CATALOGUE_MAX_DIM). The result is
# "many satisfying pieces" that scales, instead of banning big blocks outright.
MERGE_PIECE_RATIO = 0.34   # ~3 pieces across a region's long side
MERGE_MIN_CAP = 4          # smallest per-region cap (long side, in cells)


def _ratio_cap(region_xy) -> int:
    """Max piece long-side for this region: round(long_side * ratio), clamped to
    [MERGE_MIN_CAP, catalogue ceiling]. The connectivity repair pass overrides this
    with the ceiling for groups that would otherwise float / come loose."""
    xs = [x for (x, _) in region_xy]
    ys = [y for (_, y) in region_xy]
    long_side = max(max(xs) - min(xs), max(ys) - min(ys)) + 1
    cap = round(long_side * MERGE_PIECE_RATIO)
    return max(MERGE_MIN_CAP, min(cap, catalogue.CATALOGUE_MAX_DIM))


class UnsupportedBuildError(ValueError):
    """The plan isn't a sound, hand-buildable model. Two ways it can fail:
      - a piece rests on nothing (a block above z=0 with no filled cell directly below), or
      - a piece isn't connected to the rest of the build (nothing sits on it or under it to
        lock it in), so the finished model would fall apart if lifted.
    """


class _Placed:
    __slots__ = ("ox", "oy", "z", "w", "d", "material", "finish")

    def __init__(self, ox, oy, z, w, d, material, finish):
        self.ox, self.oy, self.z = ox, oy, z
        self.w, self.d = w, d
        self.material, self.finish = material, finish


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

    Only the merge needs the class (which library footprint to use): a block is studded
    or smooth. *Which* of a studded block's cells actually show a stud is no longer stored
    in the plan — it's a render-time function of cumulative occupancy (a stud is hidden as
    soon as something is stacked on it), computed per step in buildplan/iso.
    """
    exposed = {(x, y, z) for (x, y, z) in filled if (x, y, z + 1) not in filled}

    by_layer = defaultdict(set)
    for (x, y, z) in exposed:
        by_layer[z].add((x, y))

    # The foundation (lowest) layer never auto-smooths. A smooth tile is studless and
    # exposed (nothing above), and on the bottom layer it also has nothing below — so it
    # could anchor to nothing and would merge into loose pieces (the classic "wide flat
    # base whose ring falls off"). Keeping the base studded lets it merge into a solid,
    # connected foundation. An explicit per-material override can still force smooth.
    base_z = min((z for (_, _, z) in filled), default=None)

    smooth_cells = set()
    for z, xy in by_layer.items():
        if z == base_z:
            continue
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
    return class_of


def _greedy_cover(group_xy, direction, max_dim):
    """Cover a set of same-group (x,y) cells with catalogue rectangles.

    `direction` (+1 or -1) is the x growth/scan direction; alternating it per layer
    staggers seams between layers. `max_dim` caps a piece's long side (the per-region
    ratio cap, or the catalogue ceiling during connectivity repair). Deterministic given
    the inputs. Returns a list of (origin_x, origin_y, w, d) with origin at the min
    -X/-Y corner.
    """
    uncovered = set(group_xy)
    # Anchor scan order: rows front-to-back; within a row, leading edge first for this
    # direction (left->right when +1, right->left when -1).
    anchors = sorted(group_xy, key=lambda xy: (xy[1], direction * xy[0]))
    out = []
    for (ax, ay) in anchors:
        if (ax, ay) not in uncovered:
            continue
        for (w, d) in catalogue.merge_candidates(max_dim):
            cells = [(ax + direction * i, ay + j) for i in range(w) for j in range(d)]
            if all(cmp in uncovered for cmp in cells):
                for cmp in cells:
                    uncovered.discard(cmp)
                ox = min(ax, ax + direction * (w - 1))
                out.append((ox, ay, w, d))
                break
    return out


def _unsupported(placed, filled) -> list:
    """Pieces resting on nothing, in build order.

    A snap block clutches onto studs beneath it, so every block above the baseplate needs
    at least one footprint cell with a filled cell directly below. z==0 sits on the assumed
    baseplate and is always supported. (One supporting cell is enough — overhang/cantilever
    is fine, the *block* just can't float.) The smooth invariant guarantees that supporting
    cell is never a studless top, since smooth is only assigned to truly-exposed tops.
    """
    out = []
    for b in placed:
        if b.z == 0:
            continue
        supported = any((b.ox + i, b.oy + j, b.z - 1) in filled
                        for i in range(b.w) for j in range(b.d))
        if not supported:
            out.append(b)
    return out


def _disconnected(placed) -> list:
    """Blocks not joined to the main assembly by stud coupling, in build order.

    Two blocks couple only when one sits DIRECTLY ON the other: they share a footprint
    column and are exactly one layer apart (the lower's stud goes into the upper's
    underside). Same-layer neighbours do NOT couple — real snap blocks don't clutch
    side-to-side — and there's no assumed baseplate. So the test is "lift the finished
    model: does it stay in one piece?". A sound build is a single connected component;
    this returns every block outside the largest one (e.g. a flat base ring whose pieces
    have nothing above or below to lock them to the rest). Empty when fully connected.
    """
    n = len(placed)
    if n <= 1:
        return []

    # Which block owns each filled cell (blocks never overlap, so one owner per cell).
    owner = {}
    for i, b in enumerate(placed):
        for dx in range(b.w):
            for dy in range(b.d):
                owner[(b.ox + dx, b.oy + dy, b.z)] = i

    # Union-Find: union a block with whatever block sits directly on each of its cells.
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]   # path halving
            a = parent[a]
        return a

    for i, b in enumerate(placed):
        for dx in range(b.w):
            for dy in range(b.d):
                above = owner.get((b.ox + dx, b.oy + dy, b.z + 1))
                if above is not None:
                    ra, rb = find(i), find(above)
                    if ra != rb:
                        parent[ra] = rb

    roots = [find(i) for i in range(n)]
    sizes = defaultdict(int)
    for r in roots:
        sizes[r] += 1
    main = max(sizes, key=lambda r: (sizes[r], -r))   # largest; tie-break stable on index
    return [placed[i] for i in range(n) if roots[i] != main]


def _merge_all(filled, class_of, cap_for) -> list:
    """Cover every layer-group with rectangles, bottom-up.

    `cap_for((z, material, cls), region_xy)` returns the max piece long-side for that
    group, so the caller owns sizing: the ratio cap by default, lifted to the catalogue
    ceiling for groups the connectivity repair pass needs to consolidate. Returns the
    placed blocks sorted bottom-up (so both the first pass and the repair pass come out
    in build order).
    """
    placed: list[_Placed] = []
    layers = sorted({z for (_, _, z) in filled})
    for z in layers:
        groups = defaultdict(set)
        for (x, y, cz) in filled:
            if cz == z:
                groups[(filled[(x, y, z)], class_of[(x, y, z)])].add((x, y))
        direction = 1 if z % 2 == 0 else -1
        for (material, cls), xy in sorted(groups.items()):
            max_dim = cap_for((z, material, cls), xy)
            for (ox, oy, w, d) in _greedy_cover(xy, direction, max_dim):
                if cls == "smooth":
                    # INVARIANT: you can't attach a block onto a studless tile, so a
                    # smooth block must have NOTHING directly above it. Guaranteed because
                    # 'smooth' is only ever assigned to exposed-top cells (see _classify);
                    # asserted here so a future change to the rules can't silently break it.
                    assert all((ox + i, oy + j, z + 1) not in filled
                               for i in range(w) for j in range(d)), \
                        "smooth block has a filled cell directly above it"
                placed.append(_Placed(ox, oy, z, w, d, material, cls))

    placed.sort(key=lambda b: (b.z, b.oy, b.ox))   # bottom-up, deterministic within a layer
    return placed


def plan(voxel: dict, overrides: dict | None = None, allow_floating: bool = False) -> dict:
    overrides = dict(overrides or {})
    overrides.update(voxel.get("overrides") or {})

    filled = {tuple(c["cell"]): c["material"] for c in voxel.get("cells", [])}
    class_of = _classify(filled, overrides)

    # --- merge: ratio-sized pieces, then repair anything that won't hold ----------
    placed = _merge_all(filled, class_of, lambda key, xy: _ratio_cap(xy))

    floating = _unsupported(placed, filled)
    loose = _disconnected(placed)
    if floating or loose:
        # Connectivity repair: the ratio cap can split a region into rectangles where one
        # piece floats or comes loose. Re-merge ONLY the groups that own a flagged piece,
        # with the cap lifted to the catalogue ceiling (fewest, biggest pieces), so the
        # flagged piece fuses into one that reaches support / couples to the main body.
        # This is the wide-base/thin-top fix: the base consolidates into a slab the top
        # sits on. Rectangle-only — shapes only an L/T could save still fall through.
        bad = {(b.z, b.material, b.finish) for b in (floating + loose)}
        placed = _merge_all(
            filled, class_of,
            lambda key, xy: catalogue.CATALOGUE_MAX_DIM if key in bad else _ratio_cap(xy),
        )
        floating = _unsupported(placed, filled)
        loose = _disconnected(placed)

    # --- structural checks: report anything the repair couldn't save -------------
    def _fail(blocks, problem, hint):
        lines = "\n".join(f"  - {b.w}x{b.d} {b.material} at ({b.ox}, {b.oy}, {b.z})"
                          for b in blocks)
        msg = f"{len(blocks)} piece(s) {problem}:\n{lines}\n{hint}"
        if allow_floating:
            print(f"Warning: {msg}")
        else:
            raise UnsupportedBuildError(msg)

    # Some shapes can't be made sound with rectangles alone, but an L/T block would
    # bridge them — flag that so a stuck build points at the right (future) fix.
    lt_hint = ("An L- or T-shaped block might bridge this, but the auto-planner only "
               "uses rectangular blocks for now.")
    if floating:
        _fail(floating, "rest on nothing (no block directly below)",
              "Fix the model so every piece sits on the baseplate or another block, or "
              "pass --allow-floating to build it anyway.\n" + lt_hint)

    if loose:
        _fail(loose, "aren't connected to the rest of the build (nothing sits on them or "
                     "under them to lock them in)",
              "The finished model would fall apart if lifted. Fix the model so every piece "
              "interlocks with the rest, or pass --allow-floating to build it anyway.\n" + lt_hint)

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
    parser.add_argument("--allow-floating", action="store_true",
                        help="warn instead of failing when a piece rests on nothing")
    args = parser.parse_args(argv)

    voxel = vox_import.load_voxel(args.voxel, args.overrides)
    try:
        build_plan = plan(voxel, allow_floating=args.allow_floating)
    except UnsupportedBuildError as e:
        raise SystemExit(f"Can't build this model:\n{e}")
    out = Path(args.out) if args.out else Path(args.voxel).with_name(Path(args.voxel).stem + "_plan.json")
    out.write_text(json.dumps(build_plan, indent=2), encoding="utf-8")
    n = sum(len(s["add"]) for bag in build_plan["bags"] for s in bag["steps"])
    print(f"Wrote {out}  ({len(build_plan['bags'])} bags, {n} blocks)")


if __name__ == "__main__":
    main()
