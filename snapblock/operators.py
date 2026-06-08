"""
SnapBlock operators — one bpy.types.Operator per user action.

  - SNAPBLOCK_OT_add_block:   append a block from the library at the snapped cursor.
  - SNAPBLOCK_OT_apply_color: color the selected blocks with a preset material.

bpy note: every user action in Blender is a bpy.types.Operator. The class needs
a unique bl_idname in the form "category.action" (lowercase, one dot); that's the
string the UI calls via layout.operator("snapblock.add_block").
"""

import bpy

from . import constants, library, reveal


class SNAPBLOCK_OT_add_block(bpy.types.Operator):
    """Append one block from the bundled library and place it at the 3D cursor,
    snapped to the grid, inside the 'SnapBlock Build' collection."""
    bl_idname = "snapblock.add_block"
    bl_label = "Add block"
    bl_description = "Add this block at the 3D cursor, snapped to the grid"
    bl_options = {'REGISTER', 'UNDO'}   # show in the redo panel + hook Blender's native undo

    # Which block to add. The panel button sets this; the operator does exactly one
    # thing (no branching) so there's one operator per user action.
    type_id: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        # A dynamic description() classmethod overrides bl_description for the
        # tooltip — here it expands to name the real bpy call when reveal is on.
        text = "Add this block at the 3D cursor, snapped to the grid"
        if context and getattr(context.scene, "snapblock_reveal", False):
            text += ("\n\nReveal: appends a mesh object via bpy.data.libraries.load() "
                     "into the 'SnapBlock Build' collection.")
        return text

    def execute(self, context):
        # Loading can fail two friendly ways: the bundled library is missing, or the
        # requested block isn't in it. Catch both and report plainly — a traceback
        # must never reach the user.
        try:
            obj = library.append_block(self.type_id)
        except FileNotFoundError:
            self.report({'ERROR'},
                        "Couldn't find the block library that ships with SnapBlock. "
                        "Try reinstalling the add-on.")
            return {'CANCELLED'}
        except ValueError:
            self.report({'ERROR'},
                        "That block ('{}') isn't in the library yet.".format(self.type_id))
            return {'CANCELLED'}

        # Link only into the build collection (not the scene's master collection) so
        # the Outliner shows the grouping cleanly.
        library.get_build_collection(context).objects.link(obj)

        # Snap the 3D cursor to the grid and place the block there. We store nothing
        # fancy: integer grid cell = round(world / cell size), back to world coords.
        # Corner origins mean a block at a snapped corner fills whole cells exactly.
        cursor = context.scene.cursor.location
        gx = round(cursor.x / constants.U)
        gy = round(cursor.y / constants.U)
        gz = round(cursor.z / constants.H)
        obj.location = (gx * constants.U, gy * constants.U, gz * constants.H)

        # Name it for the Outliner. Blender auto-suffixes collisions (.001, .002...),
        # which gives the Block_<type>.NNN convention for free.
        obj.name = "Block_{}".format(self.type_id)

        # Make the new block the active selection so the user can immediately press G.
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj

        # Turn on grid snapping for that follow-up nudge. The placement above is
        # already exact; this just makes a manual G-drag snap to the grid too.
        # With one cell = 1.0 BU, INCREMENT snap steps by one cell at normal zoom.
        # use_snap_grid_absolute makes the steps land on absolute world cell lines
        # (multiples of 1.0) rather than relative to wherever the drag started, so a
        # dragged block lands flush with already-placed ones.
        tool_settings = context.scene.tool_settings
        tool_settings.use_snap = True
        tool_settings.snap_elements = {'INCREMENT'}
        tool_settings.use_snap_grid_absolute = True

        # Glass-box status message: name the real Blender object and where it lives.
        message = ("Added {} — a normal mesh object in the '{}' collection "
                   "(see the Outliner).").format(obj.name, constants.BUILD_COLLECTION)
        if context.scene.snapblock_reveal:
            message += " [appended via bpy.data.libraries.load]"
            reveal.note("You added an Object — a real item in your scene. "
                        "Find it in the Outliner, top-right.")
        self.report({'INFO'}, message)
        return {'FINISHED'}


def _get_or_create_material(color_name, rgba):
    """Return the shared 'SnapBlock_<colorname>' material, creating it once if
    needed. One material per color, reused across every block of that color.

    Principled BSDF only (no custom node graph). bpy note: modern materials are
    defined by their node tree, so we set use_nodes=True and edit the Principled
    node — never use_nodes=False, which gives flat viewport-only color and breaks
    the BSDF the look depends on.
    """
    mat_name = constants.MATERIAL_PREFIX + color_name
    mat = bpy.data.materials.get(mat_name)
    if mat is not None:
        return mat

    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    # Grab the Principled node by type, not by name — the label can be localised
    # or renamed, but the type is stable.
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = constants.MATERIAL_ROUGHNESS
    # Subsurface input was renamed to "Subsurface Weight" in Blender 4.x; guard the
    # set so a version mismatch degrades gracefully instead of raising KeyError.
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = constants.MATERIAL_SUBSURFACE

    # So the color is visible in Solid shading too (base color only shows in
    # Material Preview / Rendered) — beginners are often in Solid mode.
    mat.diffuse_color = rgba
    return mat


class SNAPBLOCK_OT_apply_color(bpy.types.Operator):
    """Apply a preset color to the selected blocks as a real Blender material."""
    bl_idname = "snapblock.apply_color"
    bl_label = "Apply color"
    bl_description = "Color the selected blocks with this preset"
    bl_options = {'REGISTER', 'UNDO'}

    # Which preset to apply. The swatch button sets this; one operator, one action.
    color_name: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        text = "Color the selected blocks with this preset"
        if context and getattr(context.scene, "snapblock_reveal", False):
            text += ("\n\nReveal: creates/reuses a 'SnapBlock_<color>' material "
                     "(Principled BSDF) and assigns it to each selected object.")
        return text

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets:
            self.report({'ERROR'}, "Select one or more blocks first, then pick a color.")
            return {'CANCELLED'}

        # Look the RGBA up by name so constants.COLOR_PRESETS stays the one source
        # of truth for color. Shouldn't be missing when called from the UI.
        rgba = dict(constants.COLOR_PRESETS).get(self.color_name)
        if rgba is None:
            self.report({'ERROR'}, "Unknown color '{}'.".format(self.color_name))
            return {'CANCELLED'}

        mat = _get_or_create_material(self.color_name, rgba)

        # Assign to each block's mesh data. Each placed block is its own append, so
        # meshes aren't shared — data-level assignment is the standard, safe choice.
        for obj in targets:
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

        message = ("Applied '{}' to {} block(s). Find it in the Properties panel "
                   "→ Material tab.").format(mat.name, len(targets))
        if context.scene.snapblock_reveal:
            message += " [Principled BSDF base color on each object's mesh material]"
            reveal.note("You applied a Material — the block's color and finish. "
                        "Find it in the Material tab on the right.")
        self.report({'INFO'}, message)
        return {'FINISHED'}


class SNAPBLOCK_OT_nudge(bpy.types.Operator):
    """Move the selected blocks by whole grid cells, so they always stay aligned
    to the grid — unlike a free G-drag, which can drift to a fraction of a cell."""
    bl_idname = "snapblock.nudge"
    bl_label = "Nudge block"
    bl_description = "Move the selected blocks one cell along the grid"
    bl_options = {'REGISTER', 'UNDO'}

    # How many cells to move on each axis. A panel button (or arrow-key shortcut)
    # sets exactly one of these to ±1. One operator, parameterised — still one
    # operator per user action, no branching.
    dx: bpy.props.IntProperty(default=0)
    dy: bpy.props.IntProperty(default=0)
    dz: bpy.props.IntProperty(default=0)

    @classmethod
    def poll(cls, context):
        # Enabled only when a mesh is selected. This also gates the optional arrow-
        # key shortcuts: with nothing selected the keymap item's poll fails, so the
        # keypress falls through to Blender's default arrow-key frame stepping
        # instead of being swallowed.
        return any(o.type == 'MESH' for o in context.selected_objects)

    @classmethod
    def description(cls, context, properties):
        text = "Move the selected blocks one cell along the grid"
        if context and getattr(context.scene, "snapblock_reveal", False):
            text += ("\n\nReveal: adds a whole-cell offset to each object's "
                     "location (obj.location += cells × grid size).")
        return text

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        # poll() normally prevents this, but keep a friendly guard in case the
        # operator is run from the search menu with nothing selected.
        if not targets:
            self.report({'ERROR'}, "Select a block to move.")
            return {'CANCELLED'}

        # Cells are integers; multiplying by the grid size keeps every block exactly
        # on the lattice no matter how many times you nudge. Adding to obj.location
        # is the whole operation — no bpy.ops.transform needed.
        for obj in targets:
            obj.location.x += self.dx * constants.U
            obj.location.y += self.dy * constants.U
            obj.location.z += self.dz * constants.H

        message = ("Moved {} block(s) by one cell — still on the grid."
                   .format(len(targets)))
        if context.scene.snapblock_reveal:
            message += " [obj.location += cells × grid size]"
            reveal.note("You moved the block by exactly one grid cell, so it stays "
                        "snapped — that's its Location changing.")
        self.report({'INFO'}, message)
        return {'FINISHED'}


# Each module exposes a `classes` tuple; __init__.py collects them for
# registration. Order matters: classes a panel references must register first,
# which is why operators register before panels.
classes = (
    SNAPBLOCK_OT_add_block,
    SNAPBLOCK_OT_apply_color,
    SNAPBLOCK_OT_nudge,
)
