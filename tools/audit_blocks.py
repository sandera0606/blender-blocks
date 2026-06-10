"""
Blender Blocks — block audit (READ-ONLY).

Run this inside Blender's Scripting tab. It appends the blocks from your master
library purely to *inspect* them, prints a report, and writes/saves NOTHING.

It never touches source_blocks/all_blocks.blend, and it never fixes anything —
it only tells you what's there so we can decide the origin convention together.

HOW TO RUN
  1. Open Blender 4.2+ and do File > New (a throwaway scene).
  2. Scripting tab > Text > Open > pick this file (so __file__ resolves) > Run.
  3. Copy the printed report (Window > Toggle System Console on Windows, or the
     Scripting tab's console) back to me.
  4. Close Blender WITHOUT saving — the appended blocks were only for inspection.
"""

import bpy
import os
from mathutils import Vector

# ---------------------------------------------------------------------------
# The repo root is derived from this script's own location, so it works wherever
# the repo is cloned — provided you ran the file via Text > Open (which sets
# __file__). If you pasted the script into a fresh text block instead, __file__
# won't exist; set SOURCE_PATH to your all_blocks.blend by hand below.
# ---------------------------------------------------------------------------
try:
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    REPO = ""   # e.g. r"D:\code\blender_blocks" — only needed if you pasted the script
SOURCE_PATH = os.path.join(REPO, "source_blocks", "all_blocks.blend")

COLLECTION_NAME = "blocks"   # the collection inside the source file
U = 0.002                    # 2mm grid unit, in Blender meters (see brief)
TOL = 1e-5                   # float tolerance for "is this on the grid" checks


def load_block_objects(path, collection_name):
    """Append the source 'blocks' collection and return its objects.

    bpy idiom: bpy.data.libraries.load() is a context manager. data_from lists
    what's available in the file (as *names*, i.e. strings); you copy the names
    you want onto data_to, and the actual datablocks get appended when the
    `with` block exits. link=False means APPEND (we get our own editable copy),
    as opposed to link=True which would keep a live reference to the source file.

    We append the whole 'blocks' collection rather than loose objects so we're
    scoped to exactly the blocks you care about — not anything else in the file.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            "Couldn't find the source .blend at:\n  {}\n"
            "Edit SOURCE_PATH at the top of this script.".format(path)
        )

    # Record collections that already exist so we can detect the one we append.
    # (bpy gotcha: if a 'blocks' collection somehow already existed, Blender would
    #  append the new one as 'blocks.001'. In a fresh File > New it won't, but we
    #  stay robust by diffing the collection set before/after.)
    before = set(bpy.data.collections.keys())

    with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
        if collection_name not in data_from.collections:
            raise KeyError(
                "No collection named '{}' in the source file. Found: {}".format(
                    collection_name, list(data_from.collections)
                )
            )
        data_to.collections = [collection_name]

    new_names = set(bpy.data.collections.keys()) - before
    appended_name = collection_name if collection_name in new_names else sorted(new_names)[0]
    coll = bpy.data.collections[appended_name]

    # Only mesh objects are real blocks (brief: each block is a single mesh object).
    return [ob for ob in coll.objects if ob.type == 'MESH']


def analyze(obj):
    """Measure one block. Pure reads — nothing here mutates the object.

    obj.bound_box is the 8 corners of the local-space bounding box, BEFORE the
    object's scale is applied. The local origin is (0,0,0) by definition, so we
    can read the origin's position relative to the geometry straight off these
    corners. We multiply by obj.scale to report everything in real-world meters.

    Why report scale separately from dimensions: obj.dimensions already bakes in
    scale, so a block with an unapplied 2x scale on half-size geometry would still
    show "correct" dimensions. Reporting raw scale stops that from hiding.
    """
    corners = [Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    sx, sy, sz = obj.scale

    # World-space footprint center and bottom, measured from the origin (0,0,0).
    center_x = (min(xs) + max(xs)) / 2.0 * sx
    center_y = (min(ys) + max(ys)) / 2.0 * sy
    bottom_z = min(zs) * sz

    return {
        "name": obj.name,
        "scale": (sx, sy, sz),
        # obj.dimensions = world-space size (already includes scale).
        "dims": tuple(obj.dimensions),
        # How far the origin sits from the footprint center (X,Y) and from the
        # footprint bottom (Z). All zero => bottom-center origin.
        "origin_off": (-center_x, -center_y, -bottom_z),
        "materials": [m.name if m else "<empty slot>" for m in obj.data.materials],
    }


def grid_units(value):
    """value / U, or None if it isn't a clean multiple of the grid unit."""
    n = value / U
    nearest = round(n)
    return nearest if abs(n - nearest) < (TOL / U) else None


def mm(x):
    return x * 1000.0


def main():
    print("\n" + "=" * 64)
    print("Blender Blocks block audit  (read-only — nothing is saved)")
    print("Source:", SOURCE_PATH)
    print("=" * 64)

    blocks = load_block_objects(SOURCE_PATH, COLLECTION_NAME)
    blocks.sort(key=lambda o: o.name)

    warnings = []

    for info in (analyze(b) for b in blocks):
        name = info["name"]
        sx, sy, sz = info["scale"]
        dx, dy, dz = info["dims"]
        ox, oy, oz = info["origin_off"]

        # --- per-block line ---
        gx, gy, gz = grid_units(dx), grid_units(dy), grid_units(dz)
        grid_str = "x".join(str(g) if g is not None else "?" for g in (gx, gy, gz))
        print("\n• {}".format(name))
        print("    dimensions : {:.4f} x {:.4f} x {:.4f} m  (~{} grid cells)".format(
            dx, dy, dz, grid_str))
        print("    origin off : X {:+.2f}mm  Y {:+.2f}mm  Z {:+.2f}mm "
              "(from footprint center / bottom)".format(mm(ox), mm(oy), mm(oz)))
        print("    scale      : ({:.3f}, {:.3f}, {:.3f})".format(sx, sy, sz))
        print("    materials  : {}".format(info["materials"] or "none"))

        # --- collect warnings ---
        if (round(sx, 4), round(sy, 4), round(sz, 4)) != (1.0, 1.0, 1.0):
            warnings.append("⚠ {}: scale not applied — {}".format(name, info["scale"]))
        if None in (gx, gy, gz):
            warnings.append("⚠ {}: dimensions {:.4f} x {:.4f} x {:.4f} m don't all "
                            "divide by 2mm".format(name, dx, dy, dz))
        if max(abs(ox), abs(oy), abs(oz)) > TOL:
            warnings.append("⚠ {}: origin not at bottom-center "
                            "(off X {:+.2f}mm Y {:+.2f}mm Z {:+.2f}mm)".format(
                                name, mm(ox), mm(oy), mm(oz)))
        if info["materials"]:
            warnings.append("⚠ {}: has embedded material(s) {} — will be stripped "
                            "later".format(name, info["materials"]))

    # --- summary ---
    print("\n" + "-" * 64)
    print("Cleanup audit report:")
    print("  ✓ {} blocks processed".format(len(blocks)))
    if warnings:
        for w in warnings:
            print("  " + w)
    else:
        print("  ✓ All scales applied")
        print("  ✓ All origins at bottom-center")
        print("  ✓ All dimensions on the 2mm grid")
        print("  ✓ No embedded materials")
    print("-" * 64)
    print("Nothing was written or saved. Close Blender without saving.\n")


main()
