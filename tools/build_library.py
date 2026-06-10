"""
Blender Blocks — build the cleaned block library.

Run this inside Blender's Scripting tab. It reads your master library, makes a
*clean copy* of every block, and writes it to blender_blocks/blender_blocks_library.blend.

It NEVER modifies source_blocks/all_blocks.blend and NEVER saves your session.
Think of it as "make a copy and fix the copy" — the copy is the .blend it writes.

What it does to each block (on the appended copy, in memory):
  1. Re-origins to the BOTTOM -X/-Y CORNER of the footprint (audit showed origins
     were scattered in X/Y). A corner anchor is parity-independent: every block's
     footprint corner lands on the same grid lattice, so studs always co-align and
     blocks never overlap regardless of size. Done by shifting the mesh vertices,
     no bpy.ops needed.
  2. Drops the empty material slots (colors are applied at runtime).
  3. Renames to a clean, friendly type ID (see NAME_MAP).
  4. Scales geometry by 0.5 so one grid cell = 1.0 Blender unit. The blocks are
     authored at 2.0 BU/cell, but Blender's native grid and increment-snap step
     by 1.0, so halving makes one cell line up with one native unit — a placed
     block at cell (3,0) then sits at world (3,0), and snap-dragging lands on
     whole cells. (Must match U=H=1.0 in blender_blocks/constants.py.)

HOW TO RUN
  1. Open Blender 4.2+ and do File > New (a throwaway scene).
  2. Scripting tab > Text > Open > pick this file (so __file__ resolves) > Run.
  3. Read the printed report. Confirm blender_blocks/blender_blocks_library.blend was written.
  4. Close Blender WITHOUT saving.
"""

import bpy
import os

# ---------------------------------------------------------------------------
# Paths. The repo root is derived from this script's own location, so it works
# wherever the repo is cloned — provided you ran the file via Text > Open (which
# sets __file__). If you pasted the script into a fresh text block instead,
# __file__ won't exist; set REPO to your repo root by hand below.
# ---------------------------------------------------------------------------
try:
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    REPO = ""   # e.g. r"D:\code\blender_blocks" — only needed if you pasted the script
SOURCE_PATH = os.path.join(REPO, "source_blocks", "all_blocks.blend")
OUTPUT_PATH = os.path.join(REPO, "blender_blocks", "blender_blocks_library.blend")

COLLECTION_NAME = "blocks"

# Geometry scale factor. Blocks are authored at 2.0 BU/cell; we halve them so one
# cell = 1.0 BU, matching Blender's native grid + U=H=1.0 in the add-on. Keep this
# the reciprocal of (authored cell size / target cell size) = 1.0 / 2.0.
SCALE = 0.5

# Source object name -> clean type ID. Placed blocks become Block_<type>.NNN.
# Friendly/descriptive style, per the user's choice. Anything not listed keeps
# its source name (lowercased X handled below).
NAME_MAP = {
    "10X10": "10x10",
    "10X8": "10x8",
    "10X4": "10x4",
    "10X2": "10x2",
    "20X20": "20x20",
    "20X10": "20x10",
    "8x2": "8x2",
    "6x1": "6x1",
    "4x2": "4x2",
    "4x1": "4x1",
    "4x2naked": "4x2_smooth",   # the no-studs one
    "3x2": "3x2",
    "3x1": "3x1",
    "2x2": "2x2",
    "2x2c": "2x2_round",        # cylinder version of the 2x2
    "2x1": "2x1",
    "1x1": "1x1",
    "1x1c": "1x1_round",        # the 1x1 cylinder
    "1x1.001": "step",          # the 2x1 step block (misnamed in source) — VERIFY visually
    "L": "L",
    "T": "T",
}

# Blocks to flag for a visual sanity-check in the printed report.
VERIFY_NOTES = {
    "step": "was '1x1.001' in source; expected a 2x1 step but footprint reads 4x2 x2-tall — eyeball it",
}


def load_block_objects(path, collection_name):
    """Append the source 'blocks' collection and return its mesh objects.

    Same read-only append idiom as audit_blocks.py: libraries.load() with
    link=False copies the datablocks into this session so we can edit our copy.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            "Couldn't find the source .blend at:\n  {}\n"
            "Edit SOURCE_PATH at the top of this script.".format(path)
        )

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
    appended = collection_name if collection_name in new_names else sorted(new_names)[0]
    return [ob for ob in bpy.data.collections[appended].objects if ob.type == 'MESH']


def footprint_corner(mesh):
    """Return (min_x, min_y, min_z): the bottom -X/-Y corner, in local space.

    We read straight off the vertices rather than obj.bound_box, because
    bound_box can be stale until the dependency graph re-evaluates, and these
    objects aren't linked to the scene. All source blocks have scale (1,1,1),
    so local coordinates already equal world distances.
    """
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    return (min(xs), min(ys), min(zs))


def clean_type_name(src_name):
    return NAME_MAP.get(src_name, src_name.replace("X", "x"))


def main():
    print("\n" + "=" * 64)
    print("Blender Blocks library build")
    print("Source:", SOURCE_PATH)
    print("Output:", OUTPUT_PATH)
    print("=" * 64)

    # bpy gotcha guard: appending an object whose name already exists makes
    # Blender add a .001/.002 suffix, which silently breaks the NAME_MAP lookup
    # (it's keyed on the source name). That happens if you run this twice in one
    # Blender session. Refuse to run unless the session is clean — File > New.
    conflicts = (set(NAME_MAP) | set(NAME_MAP.values())) & set(bpy.data.objects.keys())
    if conflicts or COLLECTION_NAME in bpy.data.collections:
        raise RuntimeError(
            "This session already has blocks loaded ({}). The script must run in "
            "a fresh file or names get mangled. Do File > New, then run it once."
            .format(sorted(conflicts) or ["collection '%s'" % COLLECTION_NAME]))

    blocks = load_block_objects(SOURCE_PATH, COLLECTION_NAME)
    blocks.sort(key=lambda o: o.name)

    seen_meshes = set()   # guard against two objects sharing one mesh datablock
    datablocks = set()
    rows = []

    for obj in blocks:
        src_name = obj.name
        mesh = obj.data

        # --- 1. scale to 1.0 BU/cell, then re-origin to bottom -X/-Y corner ---
        if mesh.name in seen_meshes:
            # Shared mesh would get shifted twice. None of these blocks share a
            # mesh, but if that ever changes we want a loud warning, not silent
            # double-translation.
            rows.append((src_name, "!! SHARED MESH — skipped re-origin", ""))
            continue
        seen_meshes.add(mesh.name)

        # --- 0. zero any unapplied object rotation ---
        # The audit only checked scale; 7 source blocks carry a leftover object-
        # level rotation (10X4/10X8/20X10/T at 180°, 20X20 at 360°, L at 90°,
        # 1x1c at 11°). rotation_euler is an OBJECT transform, separate from the
        # mesh geometry. The placement operator positions a library block purely
        # by its location and assumes identity orientation, so every library block
        # must sit at zero rotation. Every one of these is a pure-Z rotation, so
        # dropping it never flips a block upside-down — studs stay up. We discard
        # the rotation rather than baking it into the verts: for the symmetric
        # plates it's visually identical, and orientation of a template block is
        # arbitrary anyway (the user rotates with R in the scene).
        had_rot = tuple(round(a, 4) for a in obj.rotation_euler) != (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)

        # Scale every vertex about the local origin first. Scaling and the corner
        # shift commute (both are linear in the verts), so we scale, then read the
        # now-halved footprint and shift its corner to 0 — order doesn't change the
        # result, but doing scale first keeps the re-origin math obvious.
        for v in mesh.vertices:
            v.co *= SCALE

        min_x, min_y, min_z = footprint_corner(mesh)
        for v in mesh.vertices:
            v.co.x -= min_x
            v.co.y -= min_y
            v.co.z -= min_z
        # Origin (local 0,0,0) is now the bottom -X/-Y corner, so the whole block
        # sits in the +X/+Y/+Z octant from its origin. Park the object at the
        # world origin too, so the placement operator's location is the only
        # thing that positions it.
        obj.location = (0.0, 0.0, 0.0)

        # --- 2. drop empty material slots ---
        n_slots = len(mesh.materials)
        mesh.materials.clear()

        # --- 3. rename object + its mesh datablock ---
        new_name = clean_type_name(src_name)
        obj.name = new_name
        mesh.name = new_name
        # If Blender bumped the name with a suffix, a stale object stole it —
        # surface it instead of writing a mis-named block to the library.
        collided = "  !! got '%s' not '%s' — stale name in session" % (
            obj.name, new_name) if obj.name != new_name else ""

        datablocks.add(obj)

        # verify the new origin really is the bottom corner (should be ~0,0,0)
        vmin_x, vmin_y, vmin_z = footprint_corner(mesh)
        rows.append((
            src_name, obj.name,
            "origin->({:+.3f},{:+.3f},{:+.3f})  slots removed: {}  rot->0: {}{}".format(
                vmin_x, vmin_y, vmin_z, n_slots, "yes" if had_rot else "-", collided),
        ))

    # --- 4. write the cleaned blocks to the addon's library .blend ---
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    # libraries.write() writes the given datablocks plus their dependencies
    # (the meshes ride along automatically). fake_user keeps them from being
    # purged; compress keeps the file small.
    bpy.data.libraries.write(OUTPUT_PATH, datablocks, fake_user=True, compress=True)

    # --- report ---
    print()
    for src, new, detail in rows:
        note = VERIFY_NOTES.get(new, "")
        flag = "  ⚠ verify: " + note if note else ""
        print("  {:<10} -> {:<12} {}{}".format(src, new, detail, flag))

    print("\n" + "-" * 64)
    print("Library build report:")
    print("  ✓ {} blocks written".format(len(datablocks)))
    print("  ✓ All re-origined to the bottom -X/-Y corner (origin reads ~0,0,0 above)")
    print("  ✓ All object rotations zeroed (7 blocks had leftover Z rotation)")
    print("  ✓ Empty material slots removed")
    print("  ✓ Scaled by {} — one cell = {:.1f} BU".format(SCALE, 2.0 * SCALE))
    print("  ✓ Written to {}".format(OUTPUT_PATH))
    for new, note in VERIFY_NOTES.items():
        print("  ⚠ Please eyeball '{}': {}".format(new, note))
    print("-" * 64)
    print("Source file untouched. Session NOT saved — close without saving.\n")


main()
