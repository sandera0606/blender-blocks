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

from . import operators, panels, reveal

# All classes that need registering, in dependency order: operators first so the
# panels that reference them already exist. We unregister in reverse.
classes = (*operators.classes, *panels.classes)

# Optional arrow-key shortcuts for the cell-nudge. Each tuple is
# (key, prop_name, value): Left/Right move on X, Up/Down on Y, Page Up/Down on Z.
# Buttons in the Move panel are the primary, always-available way to nudge; these
# keys are a convenience on top.
#
# bpy gotcha: the arrow keys are bound to frame stepping in Blender's default
# keymap. We register these in the "3D View" keymap, so they only take over while
# the mouse is over the viewport, and the nudge operator's poll() returns False
# when no block is selected — so with nothing selected the keypress falls through
# to normal frame stepping. If the conflict still bothers you, just delete this
# block and the calls to _register/_unregister_keymaps(); the buttons keep working.
# (key, (dx, dy, dz)) — all three set per key so the keymap item is self-contained.
_NUDGE_KEYS = (
    ("LEFT_ARROW",  (-1, 0, 0)),
    ("RIGHT_ARROW", ( 1, 0, 0)),
    ("DOWN_ARROW",  (0, -1, 0)),
    ("UP_ARROW",    (0,  1, 0)),
    ("PAGE_DOWN",   (0, 0, -1)),
    ("PAGE_UP",     (0, 0,  1)),
)
_addon_keymaps = []   # (keymap, keymap_item) pairs, kept so we can remove them


def _register_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return   # no addon keyconfig (e.g. Blender running in background/headless)
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    for key, (dx, dy, dz) in _NUDGE_KEYS:
        kmi = km.keymap_items.new("snapblock.nudge", key, 'PRESS')
        kmi.properties.dx, kmi.properties.dy, kmi.properties.dz = dx, dy, dz
        _addon_keymaps.append((km, kmi))


def _unregister_keymaps():
    for km, kmi in _addon_keymaps:
        km.keymap_items.remove(kmi)
    _addon_keymaps.clear()


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

    # reveal mode keeps a little module-level state (the last-action note), so it
    # gets a register()/unregister() of its own alongside the class registration.
    reveal.register()

    # Arrow-key shortcuts for the nudge operator (optional convenience).
    _register_keymaps()


def unregister():
    # Mirror register() in reverse: clear reveal's note state, remove the scene
    # property, then unregister classes (reverse order so nothing is removed while
    # something still depends on it).
    _unregister_keymaps()

    reveal.unregister()

    del bpy.types.Scene.snapblock_reveal

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


# Lets you run this file directly from Blender's Text editor during development,
# not just install it as an add-on.
if __name__ == "__main__":
    register()
