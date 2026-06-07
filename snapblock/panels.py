"""
SnapBlock panels — the N-panel UI in the 3D viewport sidebar.

Structure (salvaged from the legacy add-on's main-panel + subpanel pattern):
  SNAPBLOCK_PT_main      the tab header + reveal toggle
   ├─ SNAPBLOCK_PT_blocks   grid of block buttons
   └─ SNAPBLOCK_PT_colors   grid of color swatches

bpy notes:
  - bl_space_type='VIEW_3D' + bl_region_type='UI' puts the panel in the N-panel.
  - bl_category sets the tab name. Only the MAIN panel needs it; subpanels
    inherit it from their parent (the legacy code set it on subpanels too,
    which did nothing — dropped here).
  - A subpanel is just a Panel with bl_parent_id = the parent's bl_idname.
"""

import bpy

from . import constants


class SNAPBLOCK_PT_main(bpy.types.Panel):
    bl_label = "SnapBlock"
    bl_idname = "SNAPBLOCK_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = constants.ADDON_CATEGORY

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # The reveal toggle is the headline feature — keep it at the very top.
        layout.prop(scene, "snapblock_reveal",
                    text="Show me what's really happening", toggle=True)
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
            op = grid.operator("snapblock.placeholder", text=label)
            op.info = "Block {}".format(label)


class SNAPBLOCK_PT_colors(bpy.types.Panel):
    bl_label = "Colors"
    bl_idname = "SNAPBLOCK_PT_colors"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "SNAPBLOCK_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Select blocks, then click a color:")

        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        for name, _rgba in constants.COLOR_PRESETS:
            op = grid.operator("snapblock.placeholder", text=name)
            op.info = "Color {}".format(name)


classes = (
    SNAPBLOCK_PT_main,
    SNAPBLOCK_PT_blocks,
    SNAPBLOCK_PT_colors,
)
