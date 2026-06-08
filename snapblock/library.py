"""
SnapBlock block loading — append blocks from the bundled library at runtime.

Holds the two pieces the add-block operator needs:
  - append_block(type_id): pull one block out of snapblock_library.blend.
  - get_build_collection(context): the "SnapBlock Build" collection blocks go into.

The library ships inside this package; nothing here writes to it.
"""

import os

import bpy

from . import constants

# The bundled block library lives next to this file inside the package, so resolve
# it relative to __file__ rather than hardcoding a path (works wherever the add-on
# is installed, on any OS).
LIBRARY_PATH = os.path.join(os.path.dirname(__file__), constants.LIBRARY_FILENAME)


def append_block(type_id):
    """Append the block named `type_id` from the bundled library and return the
    new Object. Raises FileNotFoundError if the library is missing, or ValueError
    if no object of that name is in it — the operator turns both into friendly,
    no-traceback messages.

    We append (link=False) rather than link so the user gets their own editable
    copy of the mesh; a linked block would be read-only and break if the library
    moved.
    """
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
