"""
Blender Blocks — a Blender add-on for building with snap-together blocks on a grid.
A toy for my own use. Every action leaves behind normal Blender objects,
materials, and collections, so I can keep editing the build by hand in Blender.

This file is the add-on entry point. Blender reads bl_info to list the add-on,
and calls register() when it's enabled and unregister() when it's disabled.
"""

bl_info = {
    "name": "Blender Blocks",
    "description": "Build with snap-together blocks on a grid. Everything stays normal, editable Blender data.",
    "author": "Sandra",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (press N) > Blender Blocks tab",
    "category": "Add Mesh",
}

import bpy

from . import prefs, driver, operators, panels

# All classes that need registering, in dependency order: prefs first (the
# PropertyGroup must exist before the AddonPreferences CollectionProperty that
# references it, and before operators/panels read it), then the driver state
# PropertyGroup (the Scene pointer below references it), then operators, then the
# panels that reference them. We unregister in reverse.
classes = (*prefs.classes, *driver.classes, *operators.classes, *panels.classes)

# Note: there are deliberately no arrow-key shortcuts for the nudge. Blender binds
# the arrow keys to frame stepping in its default keymap, and an add-on keymap item
# fights that conflict more than it helps. The Move panel buttons (panels.BLENDER_BLOCKS_PT_move)
# are the single, reliable, glass-box-visible way to nudge a block one cell.


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Attach the driver state to every Scene. Must come AFTER its PropertyGroup class is
    # registered (it's in `classes`, registered just above). PointerProperty hangs one
    # instance off each scene; it's saved in the .blend, so follow-a-manual progress
    # persists. This is the only scene-level property the add-on adds.
    bpy.types.Scene.blender_blocks_driver = bpy.props.PointerProperty(type=driver.BLENDER_BLOCKS_driver_state)


def unregister():
    # Remove the Scene pointer before unregistering its class, mirroring register().
    del bpy.types.Scene.blender_blocks_driver
    # Reverse order so nothing is removed while something still depends on it.
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


# Lets you run this file directly from Blender's Text editor during development,
# not just install it as an add-on.
if __name__ == "__main__":
    register()
