"""
Blender Blocks panels — the N-panel UI in the 3D viewport sidebar.

Structure (salvaged from the legacy add-on's main-panel + subpanel pattern):
  BLENDER_BLOCKS_PT_main      the tab header
   ├─ BLENDER_BLOCKS_PT_blocks   grid of block buttons
   └─ BLENDER_BLOCKS_PT_colors   grid of material swatches + "Add material…"

bpy notes:
  - bl_space_type='VIEW_3D' + bl_region_type='UI' puts the panel in the N-panel.
  - bl_category sets the tab name. Only the MAIN panel needs it; subpanels
    inherit it from their parent (the legacy code set it on subpanels too,
    which did nothing — dropped here).
  - A subpanel is just a Panel with bl_parent_id = the parent's bl_idname.
"""

import bpy

from . import constants, driver, prefs


class BLENDER_BLOCKS_PT_main(bpy.types.Panel):
    bl_label = "Blender Blocks"
    bl_idname = "BLENDER_BLOCKS_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = constants.ADDON_CATEGORY

    def draw(self, context):
        layout = self.layout
        layout.label(text="Pick a block below to start building.")


class BLENDER_BLOCKS_PT_blocks(bpy.types.Panel):
    bl_label = "Blocks"
    bl_idname = "BLENDER_BLOCKS_PT_blocks"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "BLENDER_BLOCKS_PT_main"

    def draw(self, context):
        layout = self.layout

        # prefs.iter_blocks yields the built-in catalogue followed by the user's custom
        # blocks — one source of truth, so captured blocks appear here for free.
        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        for type_id, label in prefs.iter_blocks(context):
            # Each button calls the same operator with a different type_id — the
            # operator-per-action split, parameterised by which block to add.
            op = grid.operator("blender_blocks.add_block", text=label)
            op.type_id = type_id

        layout.separator()
        layout.operator("blender_blocks.add_block_from_selection",
                        text="Add block from selection…", icon='ADD')

        # Removal lives here too, so it's reachable without digging into Add-on prefs.
        # Only custom blocks are listed (the built-ins can't be removed).
        prefs_block = prefs.addon_prefs(context)
        customs = list(prefs_block.custom_blocks) if prefs_block is not None else []
        if customs:
            col = layout.column(align=True)
            col.label(text="Remove a custom block:")
            for item in customs:
                row = col.row(align=True)
                row.label(text=item.name, icon='MESH_CUBE')
                op = row.operator("blender_blocks.remove_block", text="", icon='X')
                op.type_id = item.type_id


class BLENDER_BLOCKS_PT_colors(bpy.types.Panel):
    bl_label = "Materials"
    bl_idname = "BLENDER_BLOCKS_PT_colors"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "BLENDER_BLOCKS_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Select blocks, then click a material:")

        # prefs.iter_materials yields the built-in presets followed by the user's
        # custom materials — one source of truth, so new materials appear here for free.
        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        for name, _spec in prefs.iter_materials(context):
            # Same operator per swatch, parameterised by which material to apply.
            op = grid.operator("blender_blocks.apply_material", text=name)
            op.material_name = name

        layout.separator()
        col = layout.column(align=True)
        col.operator("blender_blocks.add_material", text="Add material…", icon='ADD')
        col.operator("blender_blocks.add_material_from_existing",
                     text="Add from material…", icon='MATERIAL')

        # Removal lives here too, so it's reachable without digging into Add-on prefs.
        # Only custom materials are listed (the built-in presets can't be removed).
        prefs_block = prefs.addon_prefs(context)
        customs = list(prefs_block.custom_materials) if prefs_block is not None else []
        if customs:
            col = layout.column(align=True)
            col.label(text="Remove a custom material:")
            for item in customs:
                row = col.row(align=True)
                row.label(text=item.name, icon='MATERIAL')
                op = row.operator("blender_blocks.remove_material", text="", icon='X')
                op.name = item.name


class BLENDER_BLOCKS_PT_move(bpy.types.Panel):
    """Buttons that move the selected blocks one whole cell at a time. These are
    the reliable, glass-box way to nudge — a free G-drag can snap to a fraction of
    a cell when you're zoomed in, but these always move exactly one cell."""
    bl_label = "Move"
    bl_idname = "BLENDER_BLOCKS_PT_move"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "BLENDER_BLOCKS_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Move selected blocks by one cell:")

        # align=True glues the buttons into a tidy d-pad. Each button calls the one
        # nudge operator with a different axis step (see operators.BLENDER_BLOCKS_OT_nudge).
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
                op = row.operator("blender_blocks.nudge", text=label)
                op.dx, op.dy, op.dz = dx, dy, dz


class BLENDER_BLOCKS_PT_edit(bpy.types.Panel):
    """Rotate or delete the selected blocks. Both are real Blender edits — rotate
    changes each object's Rotation (keeping it on the grid); delete removes the
    object outright (Ctrl+Z brings it back)."""
    bl_label = "Rotate & Delete"
    bl_idname = "BLENDER_BLOCKS_PT_edit"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "BLENDER_BLOCKS_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Turn the selected blocks:")

        # Two buttons calling the one rotate operator with opposite steps. As with
        # the nudge buttons, set the property on every button so the last-used value
        # never bleeds across clicks (see BLENDER_BLOCKS_PT_move's note).
        row = layout.row(align=True)
        op = row.operator("blender_blocks.rotate", text="Left 90°")
        op.steps = 1
        op = row.operator("blender_blocks.rotate", text="Right 90°")
        op.steps = -1

        layout.separator()
        # icon='TRASH' reads as "delete" at a glance.
        layout.operator("blender_blocks.delete", text="Delete selected", icon='TRASH')


class BLENDER_BLOCKS_PT_driver(bpy.types.Panel):
    """Follow a build-plan manual step by step. Hand-build each step yourself; this
    tracks where you are, lists the step's parts, ticks steps off, sorts your blocks
    into per-bag collections, and can ghost a step's blocks when you're stuck."""
    bl_label = "Follow a Manual"
    bl_idname = "BLENDER_BLOCKS_PT_driver"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_parent_id = "BLENDER_BLOCKS_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        state = context.scene.blender_blocks_driver

        # No plan loaded yet → just the open button.
        if not state.plan_filepath:
            layout.label(text="Open a build plan to follow it.")
            layout.operator("blender_blocks.driver_load", text="Load build plan…",
                            icon='FILEBROWSER')
            return

        plan = driver.get_plan(state.plan_filepath)
        if plan is None:
            layout.label(text="Can't read that plan file.", icon='ERROR')
            layout.operator("blender_blocks.driver_load", text="Load build plan…",
                            icon='FILEBROWSER')
            layout.operator("blender_blocks.driver_clear", text="Close manual", icon='X')
            return

        total = driver.step_count(plan)
        _bi, _si, bag_name, step = driver.locate(plan, state.global_index)

        # Header: model, bag, step counter + how many ticked off.
        layout.label(text=state.model_name, icon='MOD_BUILD')
        row = layout.row()
        row.label(text="Bag: {}".format(bag_name))
        row.label(text="Step {} of {}".format(state.global_index + 1, total))
        layout.label(text="{} of {} steps done".format(driver.checked_count(state), total))

        # Parts list for this step (derived, like the manual's).
        box = layout.box()
        box.label(text="This step needs:")
        parts = driver.parts_for_step(step)
        if parts:
            for line in parts:
                box.label(text=line, icon='MESH_CUBE')
        else:
            box.label(text="(nothing — an empty step)")

        # Honor-system checkoff for the current step.
        checked = driver.is_checked(state, state.global_index)
        op = layout.operator(
            "blender_blocks.driver_toggle_check",
            text="Done — built it" if checked else "Mark this step done",
            icon='CHECKBOX_HLT' if checked else 'CHECKBOX_DEHLT',
            depress=checked,
        )
        op.index = state.global_index

        # Navigation: one operator, two buttons (set every prop on each — last-used bleed).
        row = layout.row(align=True)
        op = row.operator("blender_blocks.driver_goto", text="◀ Prev")
        op.delta, op.absolute = -1, -1
        op = row.operator("blender_blocks.driver_goto", text="Next ▶")
        op.delta, op.absolute = 1, -1

        # Ghost hint: an operator (not a bare prop) so it can build/clear the previews;
        # depress shows whether it's currently on.
        layout.operator(
            "blender_blocks.driver_toggle_ghost",
            text="Ghost hint: on" if state.show_ghost else "Ghost hint: off",
            icon='GHOST_ENABLED', depress=state.show_ghost,
        )

        layout.separator()
        layout.operator("blender_blocks.driver_clear", text="Close manual", icon='X')


classes = (
    BLENDER_BLOCKS_PT_main,
    BLENDER_BLOCKS_PT_blocks,
    BLENDER_BLOCKS_PT_colors,
    BLENDER_BLOCKS_PT_move,
    BLENDER_BLOCKS_PT_edit,
    BLENDER_BLOCKS_PT_driver,
)
