"""
SnapBlock — view the cleaned library (throwaway viewer).

snapblock_library.blend is a parts bin: the blocks live in it as loose
datablocks, NOT linked to any scene, so opening the file shows an empty
viewport. This script appends them all into the current scene and lays them
out in a row on the floor so you can look at each one.

HOW TO RUN
  1. Open Blender 4.2+ and do File > New (throwaway scene).
  2. Scripting tab > Text > Open > pick this file (so __file__ resolves) > Run.
  3. Hover the mouse over the 3D viewport and press Home to frame everything.
  4. Click any block in the Outliner to see its name. Close without saving.
"""

import bpy
import os

# Repo root is derived from this script's location, so it works wherever the
# repo is cloned — provided you ran the file via Text > Open (which sets
# __file__). If you pasted the script instead, set LIBRARY_PATH by hand below.
try:
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    REPO = ""   # e.g. r"D:\code\snapblock" — only needed if you pasted the script
LIBRARY_PATH = os.path.join(REPO, "snapblock", "snapblock_library.blend")
GAP = 1.0   # space between blocks, in Blender units (one grid cell)


def main():
    if not os.path.exists(LIBRARY_PATH):
        raise FileNotFoundError("No library at:\n  {}".format(LIBRARY_PATH))

    # Append every object from the library. Inside the `with`, data_from.objects
    # is a list of NAMES (strings); we copy them to data_to to request them.
    with bpy.data.libraries.load(LIBRARY_PATH, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)

    # bpy gotcha: after the `with` exits, Blender has SWAPPED data_to.objects
    # from the names you asked for to the real loaded Object datablocks. Read
    # them from data_to.objects directly — don't try to look them up by name.
    scene_coll = bpy.context.scene.collection
    appended = [o for o in data_to.objects if o is not None]
    appended.sort(key=lambda o: o.name)

    # Loose appended objects aren't in any collection yet — link them to the
    # scene so they actually draw, then space them along +X. Origins are at the
    # bottom -X/-Y corner, so each block extends in +X/+Y/+Z from its location;
    # setting location.z = 0 sits each block on the floor.
    x_cursor = 0.0
    print("\nLayout (left to right along +X):")
    for obj in appended:
        if obj.name not in scene_coll.objects:
            scene_coll.objects.link(obj)
        obj.location = (x_cursor, 0.0, 0.0)
        print("  x={:7.2f}  {}".format(obj.location.x, obj.name))
        x_cursor += obj.dimensions.x + GAP

    print("\n{} blocks placed. Hover the viewport and press Home to frame all."
          .format(len(appended)))
    print("Don't save this file.\n")


main()
