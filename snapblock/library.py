"""
SnapBlock block loading — append blocks from the library at runtime, and store the
ones the user captures from a selection.

Holds the pieces the block operators need:
  - append_block(type_id): pull one block out of the library (custom one if present,
    else the bundled snapblock_library.blend).
  - write_custom_block / delete_custom_block: the geometry side of a captured block.
  - footprint_min / footprint_dims: read a mesh's grid footprint off its verts.
  - get_build_collection(context): the "SnapBlock Build" collection blocks go into.

Nothing here writes to the bundled library; custom blocks go to the per-user dir.
"""

import os

import bpy

from . import constants, prefs

# The bundled block library lives next to this file inside the package, so resolve
# it relative to __file__ rather than hardcoding a path (works wherever the add-on
# is installed, on any OS).
LIBRARY_PATH = os.path.join(os.path.dirname(__file__), constants.LIBRARY_FILENAME)


def _append_only_object(path):
    """Append the single object out of a one-object .blend (our custom-block files)
    and return it. Reads "the first object", NOT by name — a custom file holds exactly
    one block, and reading by index sidesteps any rename Blender might have applied
    when the object was written. Raises ValueError if the file somehow holds none."""
    with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
        if not data_from.objects:
            raise ValueError(path)
        data_to.objects = [data_from.objects[0]]
    return data_to.objects[0]


def append_block(type_id):
    """Append the block `type_id` and return the new Object. Looks for a user-captured
    custom block first (its own .blend), then falls back to the bundled library.

    Raises FileNotFoundError if the bundled library is missing, or ValueError if no
    block of that id exists anywhere — the operator turns both into friendly,
    no-traceback messages.

    We append (link=False) rather than link so the user gets their own editable copy
    of the mesh; a linked block would be read-only and break if the library moved.
    """
    # Custom blocks are checked first by a cheap path test. A custom type_id can never
    # equal a built-in id (prefs.block_name_exists forbids it at capture), so there's
    # no ambiguity about which one a given id means.
    custom_path = prefs.custom_block_path(type_id)
    if os.path.exists(custom_path):
        return _append_only_object(custom_path)

    if not os.path.exists(LIBRARY_PATH):
        raise FileNotFoundError(LIBRARY_PATH)

    # libraries.load opens the .blend read-only. Inside the `with`, data_from lists
    # the NAMES available; assigning into data_to requests those datablocks.
    with bpy.data.libraries.load(LIBRARY_PATH, link=False) as (data_from, data_to):
        if type_id not in data_from.objects:
            raise ValueError(type_id)
        data_to.objects = [type_id]

    # bpy gotcha: after the `with` exits, Blender has SWAPPED data_to.objects from
    # the names you asked for to the real loaded Object datablocks. Read the result
    # from data_to.objects directly — don't look it up by name. (Same idiom as
    # tools/view_library.py.)
    return data_to.objects[0]


def footprint_min(mesh):
    """Return (min_x, min_y, min_z): the bottom -X/-Y corner of a mesh in local space,
    read straight off the vertices. Same approach as tools/build_library.py — read
    verts, not obj.bound_box, which can be stale until the depsgraph re-evaluates."""
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    return (min(xs), min(ys), min(zs))


def footprint_dims(mesh):
    """Return (dx, dy, dz): the mesh's bounding-box size in local space, off its
    vertices. Used to check a captured block's footprint lands on whole grid cells."""
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def write_custom_block(obj, type_id):
    """Write one captured block to its own .blend under the per-user custom-blocks dir.

    libraries.write() writes the given datablocks plus dependencies (the mesh rides
    along), overwriting the file. One object per file means no read-modify-write merge
    — adding is a single write, removing is a single delete. fake_user keeps the block
    from being purged; compress keeps the file small."""
    bpy.data.libraries.write(prefs.custom_block_path(type_id), {obj},
                             fake_user=True, compress=True)


def delete_custom_block(type_id):
    """Delete a custom block's .blend. Tolerates a missing file so removing a stale
    registry entry (whose file is already gone) still succeeds."""
    path = prefs.custom_block_path(type_id)
    if os.path.exists(path):
        os.remove(path)


def get_build_collection(context):
    """Return the 'SnapBlock Build' collection, creating it (and linking it to the
    scene) if it doesn't exist yet. Placed blocks live here so the grouping shows
    up in the Outliner — collections are a real Blender feature we want to surface.
    """
    name = constants.BUILD_COLLECTION
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        context.scene.collection.children.link(collection)
    return collection
