"""
SnapBlock — a Blender add-on that gives beginners a snap-block toy on top of a
real Blender scene. Glass-box by design: every action leaves behind normal
Blender objects, materials, and collections.

This file is the add-on entry point. Blender reads bl_info to list the add-on,
and calls register() when it's enabled and unregister() when it's disabled.
"""

bl_info = {
    "name": "SnapBlock",
    "description": "Build with snap-together blocks on a grid — a friendly, glass-box way into Blender.",
    "author": "Sandra",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (press N) > SnapBlock tab",
    "category": "Add Mesh",
}

import bpy

from . import operators, panels

# All classes that need registering, in dependency order: operators first so the
# panels that reference them already exist. We unregister in reverse.
classes = (*operators.classes, *panels.classes)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Scene properties live on the data, not on a class, so they're registered
    # separately. Storing on bpy.types.Scene means the value is saved in the
    # .blend and is per-scene. (The legacy add-on used a PropertyGroup; a single
    # bool doesn't need one.)
    bpy.types.Scene.snapblock_reveal = bpy.props.BoolProperty(
        name="Show me what's really happening",
        description="Reveal the real Blender operations behind each button",
        default=False,
    )


def unregister():
    # Mirror register(): remove the scene property, then unregister classes in
    # reverse order so nothing is removed while something still depends on it.
    del bpy.types.Scene.snapblock_reveal

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


# Lets you run this file directly from Blender's Text editor during development,
# not just install it as an add-on.
if __name__ == "__main__":
    register()
