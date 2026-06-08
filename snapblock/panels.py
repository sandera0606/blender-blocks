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

import textwrap

import bpy

from . import constants, reveal


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
            # Each button calls the same operator with a different type_id — the
            # operator-per-action split, parameterised by which block to add.
            op = grid.operator("snapblock.add_block", text=label)
            op.type_id = type_id


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
            # Same operator per swatch, parameterised by which preset to apply.
            op = grid.operator("snapblock.apply_color", text=name)
            op.color_name = name


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


class SNAPBLOCK_PT_lastaction(bpy.types.Panel):
    """A calm, stay-put explanation of the last action — the replacement for the
    old viewport flash. Only appears when reveal mode is on (poll() controls that),
    and updates each time an operator records a note via reveal.note()."""
    bl_label = "What just happened"
    bl_idname = "SNAPBLOCK_PT_lastaction"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "SNAPBLOCK_PT_main"

    @classmethod
    def poll(cls, context):
        return context.scene.snapblock_reveal

    def draw(self, context):
        layout = self.layout
        note = reveal.get_note()
        if not note:
            # Before the first action there's nothing to explain yet.
            layout.label(text="Do something and I'll explain it here.")
            return
        # bpy note: layout.label doesn't wrap, so wrap the text ourselves and
        # emit one label per line (same approach as the glossary).
        box = layout.box()
        first = True
        for line in textwrap.wrap(note, width=34):
            box.label(text=line, icon='INFO' if first else 'BLANK1')
            first = False


class SNAPBLOCK_PT_glossary(bpy.types.Panel):
    """Plain-English definitions of the Blender words SnapBlock uses. Only appears
    when reveal mode is on — that's what poll() controls."""
    bl_label = "What these words mean"
    bl_idname = "SNAPBLOCK_PT_glossary"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "SNAPBLOCK_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        # A panel is shown only if poll() returns True — so the glossary is hidden
        # entirely until the user turns reveal mode on.
        return context.scene.snapblock_reveal

    def draw(self, context):
        layout = self.layout
        for term, definition in reveal.CONCEPTS:
            box = layout.box()
            box.label(text=term, icon='INFO')
            # bpy note: layout.label doesn't wrap, so wrap the text ourselves and
            # emit one label per line.
            for line in textwrap.wrap(definition, width=34):
                box.label(text=line)


classes = (
    SNAPBLOCK_PT_main,
    SNAPBLOCK_PT_blocks,
    SNAPBLOCK_PT_colors,
    SNAPBLOCK_PT_move,
    SNAPBLOCK_PT_lastaction,
    SNAPBLOCK_PT_glossary,
)
