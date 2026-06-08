"""
SnapBlock panels — the N-panel UI in the 3D viewport sidebar.

Structure (salvaged from the legacy add-on's main-panel + subpanel pattern):
  SNAPBLOCK_PT_main      the tab header
   ├─ SNAPBLOCK_PT_blocks   grid of block buttons
   └─ SNAPBLOCK_PT_colors   grid of material swatches + "Add material…"

bpy notes:
  - bl_space_type='VIEW_3D' + bl_region_type='UI' puts the panel in the N-panel.
  - bl_category sets the tab name. Only the MAIN panel needs it; subpanels
    inherit it from their parent (the legacy code set it on subpanels too,
    which did nothing — dropped here).
  - A subpanel is just a Panel with bl_parent_id = the parent's bl_idname.
"""

import bpy

from . import constants, prefs


class SNAPBLOCK_PT_main(bpy.types.Panel):
    bl_label = "SnapBlock"
    bl_idname = "SNAPBLOCK_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = constants.ADDON_CATEGORY

    def draw(self, context):
        layout = self.layout
        layout.label(text="Pick a block below to start building.")


class SNAPBLOCK_PT_blocks(bpy.types.Panel):
    bl_label = "Blocks"
    bl_idname = "SNAPBLOCK_PT_blocks"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "SNAPBLOCK_PT_main"

    def draw(self, context):
        layout = self.layout

        # grid_flow lays buttons out in a tidy, auto-wrapping grid.
        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        for type_id, label in constants.BLOCK_TYPES:
            # Each button calls the same operator with a different type_id — the
            # operator-per-action split, parameterised by which block to add.
            op = grid.operator("snapblock.add_block", text=label)
            op.type_id = type_id


class SNAPBLOCK_PT_colors(bpy.types.Panel):
    bl_label = "Materials"
    bl_idname = "SNAPBLOCK_PT_colors"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "SNAPBLOCK_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Select blocks, then click a material:")

        # prefs.iter_materials yields the built-in presets followed by the user's
        # custom materials — one source of truth, so new materials appear here for free.
        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        for name, _spec in prefs.iter_materials(context):
            # Same operator per swatch, parameterised by which material to apply.
            op = grid.operator("snapblock.apply_material", text=name)
            op.material_name = name

        layout.separator()
        col = layout.column(align=True)
        col.operator("snapblock.add_material", text="Add material…", icon='ADD')
        col.operator("snapblock.add_material_from_existing",
                     text="Add from material…", icon='MATERIAL')


class SNAPBLOCK_PT_move(bpy.types.Panel):
    """Buttons that move the selected blocks one whole cell at a time. These are
    the reliable, glass-box way to nudge — a free G-drag can snap to a fraction of
    a cell when you're zoomed in, but these always move exactly one cell."""
    bl_label = "Move"
    bl_idname = "SNAPBLOCK_PT_move"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "SNAPBLOCK_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Move selected blocks by one cell:")

        # align=True glues the buttons into a tidy d-pad. Each button calls the one
        # nudge operator with a different axis step (see operators.SNAPBLOCK_OT_nudge).
        #
        # bpy gotcha: Blender remembers an operator's last-used property values, so a
        # button that sets only op.dx would let dy/dz carry over from the *previous*
        # click (e.g. +X right after Up would still move in Z). Set all three on every
        # button so each one is self-contained.
        moves = (
            ("−X", (-1, 0, 0)), ("+X", (1, 0, 0)),
            ("−Y", (0, -1, 0)), ("+Y", (0, 1, 0)),
            ("Down", (0, 0, -1)), ("Up", (0, 0, 1)),
        )
        col = layout.column(align=True)
        for i in range(0, len(moves), 2):
            row = col.row(align=True)
            for label, (dx, dy, dz) in moves[i:i + 2]:
                op = row.operator("snapblock.nudge", text=label)
                op.dx, op.dy, op.dz = dx, dy, dz


class SNAPBLOCK_PT_edit(bpy.types.Panel):
    """Rotate or delete the selected blocks. Both are real Blender edits — rotate
    changes each object's Rotation (keeping it on the grid); delete removes the
    object outright (Ctrl+Z brings it back)."""
    bl_label = "Rotate & Delete"
    bl_idname = "SNAPBLOCK_PT_edit"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "SNAPBLOCK_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Turn the selected blocks:")

        # Two buttons calling the one rotate operator with opposite steps. As with
        # the nudge buttons, set the property on every button so the last-used value
        # never bleeds across clicks (see SNAPBLOCK_PT_move's note).
        row = layout.row(align=True)
        op = row.operator("snapblock.rotate", text="Left 90°")
        op.steps = 1
        op = row.operator("snapblock.rotate", text="Right 90°")
        op.steps = -1

        layout.separator()
        # icon='TRASH' reads as "delete" at a glance.
        layout.operator("snapblock.delete", text="Delete selected", icon='TRASH')


classes = (
    SNAPBLOCK_PT_main,
    SNAPBLOCK_PT_blocks,
    SNAPBLOCK_PT_colors,
    SNAPBLOCK_PT_move,
    SNAPBLOCK_PT_edit,
)
