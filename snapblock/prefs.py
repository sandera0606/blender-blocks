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

import bpy

from . import constants


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

    def draw(self, context):
        layout = self.layout
        layout.label(text="Your custom materials (add them from the SnapBlock sidebar):")
        if not self.custom_materials:
            layout.label(text="None yet.", icon='INFO')
            return
        for item in self.custom_materials:
            row = layout.row(align=True)
            row.label(text=item.name, icon='MATERIAL')
            # Set the name on the remove button so it targets this row.
            op = row.operator("snapblock.remove_material", text="", icon='X')
            op.name = item.name


def addon_prefs(context):
    """The SnapBlockPreferences block for this add-on."""
    return context.preferences.addons[__package__].preferences


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
    for item in addon_prefs(context).custom_materials:
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


classes = (
    SNAPBLOCK_material_item,
    SnapBlockPreferences,
)
