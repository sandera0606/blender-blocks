"""
SnapBlock preferences — the add-on's persistent, user-authored store.

Holds the custom-material library: materials Sandra makes inside Blender, saved in
the add-on's preferences so they survive across sessions and are available in every
file (not just the one they were made in).

bpy notes:
  - This is SnapBlock's first stateful piece. User content lives here in
    AddonPreferences (global to the add-on, per user) rather than on the scene, so a
    material made once shows up everywhere. AddonPreferences is the standard home
    for "settings that belong to the add-on, not to a particular .blend".
  - Glass-box is preserved: an entry here is only a *recipe*. What actually lands on
    a block is still a normal SnapBlock_<name> material (built in
    operators._get_or_create_material), which survives even if the add-on is removed.
"""

import os
import re

import bpy

from . import constants


# Shown when a save-a-material action runs but the add-on isn't enabled (so there's
# nowhere to persist customs). Plain English, points at the fix, no Python jargon.
PREFS_DISABLED_MSG = (
    "Custom materials need SnapBlock turned on in Edit ▸ Preferences ▸ Add-ons. "
    "The built-in colors still work without it."
)

# Same situation for capturing custom blocks: nowhere to record them if the add-on
# isn't enabled. The built-in blocks still work without it.
BLOCKS_DISABLED_MSG = (
    "Custom blocks need SnapBlock turned on in Edit ▸ Preferences ▸ Add-ons. "
    "The built-in blocks still work without it."
)


class SNAPBLOCK_block_item(bpy.types.PropertyGroup):
    """One custom block the user captured from a selection. Only a *pointer*: the
    geometry lives in its own .blend under the custom-blocks dir (custom_block_path);
    this just records what exists and what to call it.

      name    - the display label the user typed, e.g. "My Wedge".
      type_id - a filename/Outliner-safe slug of it, e.g. "my_wedge". Used for the
                .blend filename and the placed object's Block_<type_id> name, so it
                must match what library.append_block loads. Built by slug() at capture.
    """
    name: bpy.props.StringProperty(name="Name")
    type_id: bpy.props.StringProperty(name="Type ID")


class SNAPBLOCK_material_item(bpy.types.PropertyGroup):
    """One user-made material recipe. The finish preset only seeds these values at
    creation time; what's stored here is the final look."""
    # PropertyGroup gives a "name" StringProperty for free, but declare it so its
    # UI label is explicit.
    name: bpy.props.StringProperty(name="Name")
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', size=3, min=0.0, max=1.0,
        default=(0.8, 0.8, 0.8),
    )
    roughness: bpy.props.FloatProperty(name="Roughness", min=0.0, max=1.0, default=0.4)
    opacity: bpy.props.FloatProperty(name="Opacity", min=0.0, max=1.0, default=1.0)
    transmission: bpy.props.FloatProperty(name="Transmission", min=0.0, max=1.0, default=0.0)


class SnapBlockPreferences(bpy.types.AddonPreferences):
    # bpy gotcha: bl_idname MUST equal the add-on's package name, or
    # context.preferences.addons[__package__] can't find these preferences. Using
    # __package__ keeps it correct whether installed as a legacy add-on ("snapblock")
    # or a 4.2 extension ("bl_ext...snapblock").
    bl_idname = __package__

    custom_materials: bpy.props.CollectionProperty(type=SNAPBLOCK_material_item)
    custom_blocks: bpy.props.CollectionProperty(type=SNAPBLOCK_block_item)

    def draw(self, context):
        layout = self.layout

        layout.label(text="Your custom materials (add them from the SnapBlock sidebar):")
        if not self.custom_materials:
            layout.label(text="None yet.", icon='INFO')
        for item in self.custom_materials:
            row = layout.row(align=True)
            row.label(text=item.name, icon='MATERIAL')
            # Set the name on the remove button so it targets this row.
            op = row.operator("snapblock.remove_material", text="", icon='X')
            op.name = item.name

        layout.separator()

        layout.label(text="Your custom blocks (add them from the SnapBlock sidebar):")
        if not self.custom_blocks:
            layout.label(text="None yet.", icon='INFO')
        for item in self.custom_blocks:
            row = layout.row(align=True)
            row.label(text=item.name, icon='MESH_CUBE')
            # remove_block targets the row by its type_id (the stable slug).
            op = row.operator("snapblock.remove_block", text="", icon='X')
            op.type_id = item.type_id


def addon_prefs(context):
    """The SnapBlockPreferences block for this add-on, or None if the add-on isn't
    enabled through Blender's add-on system.

    bpy gotcha: AddonPreferences only become reachable via
    context.preferences.addons[<pkg>] once the add-on has been *enabled* (the
    Add-ons list / addon_enable creates that entry). If the package was merely
    imported and register()-ed directly — e.g. loaded off sys.path by the dev
    bridge — the entry doesn't exist and indexing raises KeyError. We return None
    instead so read paths fall back to the built-in presets rather than crashing
    the whole panel on redraw."""
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon is not None else None


def _spec(name, color, roughness, opacity, transmission):
    """Bundle a material's look into a plain dict the operators consume."""
    return {
        "name": name,
        "color": tuple(color),
        "roughness": roughness,
        "opacity": opacity,
        "transmission": transmission,
    }


def iter_materials(context):
    """Yield (name, spec) for every available material: the built-in color presets
    first, then the user's custom materials. The single source of truth for 'what
    materials exist' — both the panel and the apply operator read this."""
    for name, rgba in constants.COLOR_PRESETS:
        # Presets are flat opaque colors at the default plastic roughness.
        yield name, _spec(name, rgba[:3], constants.MATERIAL_ROUGHNESS, 1.0, 0.0)
    # Custom materials live in AddonPreferences, which only exist when the add-on is
    # enabled. If it isn't (e.g. dev-bridge load), there simply are no customs yet.
    prefs_block = addon_prefs(context)
    if prefs_block is None:
        return
    for item in prefs_block.custom_materials:
        yield item.name, _spec(item.name, item.color, item.roughness,
                               item.opacity, item.transmission)


def get_material_spec(context, name):
    """Return the spec dict for `name`, or None if there's no such material."""
    for mat_name, spec in iter_materials(context):
        if mat_name == name:
            return spec
    return None


def material_name_exists(context, name):
    """Case-insensitive check against all preset and custom names — used to stop
    duplicate names, which would otherwise collide on the shared SnapBlock_<name>
    material (one material per name)."""
    lowered = name.casefold()
    return any(n.casefold() == lowered for n, _ in iter_materials(context))


# --- Custom blocks ---------------------------------------------------------
# Blocks are geometry, not a small recipe, so (unlike materials) they can't live
# entirely in prefs. The prefs entry is a pointer; the mesh lives in its own .blend
# under a per-user CONFIG dir, so an add-on reinstall can't wipe it.

def slug(name):
    """Turn a display name into a filesystem/Outliner-safe type_id: lowercase, with
    every run of non-alphanumeric characters collapsed to a single underscore and the
    ends trimmed. "My Wedge!" -> "my_wedge". Returns "" if nothing usable is left, so
    the caller can reject an all-punctuation name."""
    return re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")


def custom_blocks_dir():
    """The per-user directory holding one .blend per custom block, created on demand.

    bpy idiom: bpy.utils.user_resource('CONFIG') is Blender's per-user config dir
    (version-specific). Putting custom blocks under it — NOT inside the add-on package
    — means reinstalling/updating the add-on never deletes them. create=True makes the
    subfolders if missing."""
    return bpy.utils.user_resource('CONFIG', path=constants.CUSTOM_BLOCKS_DIRNAME,
                                   create=True)


def custom_block_path(type_id):
    """Absolute path to one custom block's .blend. Deterministic from type_id, so
    library.append_block can find it without consulting prefs."""
    return os.path.join(custom_blocks_dir(), type_id + ".blend")


def iter_blocks(context):
    """Yield (type_id, label) for every available block: the built-in catalogue first,
    then the user's custom blocks. The single source of truth for 'what blocks exist' —
    the Blocks panel reads this so customs appear for free (mirrors iter_materials)."""
    for type_id, label in constants.BLOCK_TYPES:
        yield type_id, label
    prefs_block = addon_prefs(context)
    if prefs_block is None:
        return
    for item in prefs_block.custom_blocks:
        yield item.type_id, item.name


def block_name_exists(context, type_id):
    """Case-insensitive check of a candidate type_id against built-in ids and existing
    custom ids. Stops collisions — including a custom name that slugs onto a built-in
    id (e.g. "2x2") and would otherwise shadow it in append_block."""
    lowered = type_id.casefold()
    return any(tid.casefold() == lowered for tid, _ in iter_blocks(context))


classes = (
    SNAPBLOCK_block_item,
    SNAPBLOCK_material_item,
    SnapBlockPreferences,
)
