"""
Blender Blocks operators — one bpy.types.Operator per user action.

  - BLENDER_BLOCKS_OT_add_block:       append a block from the library at the snapped cursor.
  - BLENDER_BLOCKS_OT_apply_material:  give the selected blocks a material (preset or custom).
  - BLENDER_BLOCKS_OT_add_material:    make a custom material and save it to the library.
  - BLENDER_BLOCKS_OT_add_material_from_existing: capture an existing material into the library.
  - BLENDER_BLOCKS_OT_remove_material: drop a custom material from the library.
  - BLENDER_BLOCKS_OT_nudge:           move the selected blocks by whole grid cells.
  - BLENDER_BLOCKS_OT_rotate:          turn the selected blocks 90° about Z, staying on grid.
  - BLENDER_BLOCKS_OT_delete:          remove the selected blocks from the scene.

bpy note: every user action in Blender is a bpy.types.Operator. The class needs
a unique bl_idname in the form "category.action" (lowercase, one dot); that's the
string the UI calls via layout.operator("blender_blocks.add_block").
"""

import math

import bpy
from mathutils import Matrix, Vector

from . import constants, driver, library, prefs


class BLENDER_BLOCKS_OT_add_block(bpy.types.Operator):
    """Append one block from the bundled library and place it at the 3D cursor,
    snapped to the grid, inside the 'Blender Blocks Build' collection."""
    bl_idname = "blender_blocks.add_block"
    bl_label = "Add block"
    bl_description = "Add this block at the 3D cursor, snapped to the grid"
    bl_options = {'REGISTER', 'UNDO'}   # show in the redo panel + hook Blender's native undo

    # Which block to add. The panel button sets this; the operator does exactly one
    # thing (no branching) so there's one operator per user action.
    type_id: bpy.props.StringProperty()

    def execute(self, context):
        # Loading can fail two friendly ways: the bundled library is missing, or the
        # requested block isn't in it. Catch both and report plainly — a traceback
        # must never reach the user.
        try:
            obj = library.append_block(self.type_id)
        except FileNotFoundError:
            self.report({'ERROR'},
                        "Couldn't find the block library that ships with Blender Blocks. "
                        "Try reinstalling the add-on.")
            return {'CANCELLED'}
        except ValueError:
            self.report({'ERROR'},
                        "That block ('{}') isn't in the library yet.".format(self.type_id))
            return {'CANCELLED'}

        # Link into the build collection — or, while a manual is loaded, the current
        # bag's collection (driver.current_target_collection), so a guided build sorts
        # itself into per-bag groups in the Outliner. Either way, not the scene's master
        # collection, so the grouping reads cleanly.
        driver.current_target_collection(context).objects.link(obj)

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

        # Status message: name the real Blender object and where it lives.
        message = ("Added {} — a normal mesh object in the '{}' collection "
                   "(see the Outliner).").format(obj.name, constants.BUILD_COLLECTION)
        self.report({'INFO'}, message)
        return {'FINISHED'}


def _whole_cells(value, cell_size):
    """If `value` is a whole number of cells (within GRID_SNAP_TOL), return that
    integer count; otherwise return None. Used to check a captured block's footprint
    snaps to the grid before we accept it."""
    cells = value / cell_size
    nearest = round(cells)
    if nearest >= 1 and abs(cells - nearest) <= constants.GRID_SNAP_TOL:
        return nearest
    return None


class BLENDER_BLOCKS_OT_add_block_from_selection(bpy.types.Operator):
    """Capture the active object as a new block in your library, so it shows up as a
    button in every file. Blender Blocks makes a clean copy: it bakes in the object's
    rotation/scale, moves the origin to the bottom corner, and drops its materials —
    your original object is left untouched. The footprint must be a whole number of
    cells so the block snaps to the grid."""
    bl_idname = "blender_blocks.add_block_from_selection"
    bl_label = "Add block from selection"
    bl_description = "Capture the active object as a custom block in your library"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(name="Block name", default="")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def invoke(self, context, event):
        # Default the name to the active object's name (only if the user hasn't typed
        # one yet), then pop the dialog so they can rename before it's captured.
        if not self.name and context.active_object is not None:
            self.name = context.active_object.name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        target = context.active_object
        if target is None or target.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object to capture as a block.")
            return {'CANCELLED'}

        name = self.name.strip()
        if not name:
            self.report({'ERROR'}, "Give the block a name first.")
            return {'CANCELLED'}

        type_id = prefs.slug(name)
        if not type_id:
            self.report({'ERROR'},
                        "That name has no letters or numbers I can use — try a plain "
                        "name like 'My Wedge'.")
            return {'CANCELLED'}

        # Need somewhere to record the block; bail early (before any geometry work) if
        # the add-on isn't enabled.
        prefs_block = prefs.addon_prefs(context)
        if prefs_block is None:
            self.report({'ERROR'}, prefs.BLOCKS_DISABLED_MSG)
            return {'CANCELLED'}

        if prefs.block_name_exists(context, type_id):
            self.report({'ERROR'},
                        "A block called '{}' already exists — pick another name."
                        .format(name))
            return {'CANCELLED'}

        # Work on a COPY of the mesh so the user's object is never touched. bpy note:
        # data.copy() copies the base mesh (modifiers are NOT applied — apply them
        # first if you want them baked in).
        mesh = target.data.copy()
        # Bake the object's full world transform (location + rotation + scale) into the
        # vertices — this captures the block as you see it and "applies" scale/rotation
        # in one step. mesh.transform multiplies every vertex by the matrix.
        mesh.transform(target.matrix_world)
        # Colors are applied at runtime, like every built-in block — drop any materials.
        mesh.materials.clear()

        # Re-origin to the bottom -X/-Y corner (same convention as every built-in block),
        # so a placed block fills whole cells from its origin.
        min_x, min_y, min_z = library.footprint_min(mesh)
        mesh.transform(Matrix.Translation((-min_x, -min_y, -min_z)))

        # Refuse an off-grid footprint rather than silently rounding it (per the chosen
        # validation rule). Only X/Y are checked: a block legitimately stands a little
        # over 1.0 tall because studs add height (see constants.H).
        dx, dy, _dz = library.footprint_dims(mesh)
        cells_x = _whole_cells(dx, constants.U)
        cells_y = _whole_cells(dy, constants.U)
        if cells_x is None or cells_y is None:
            # Clean up the throwaway mesh copy before bailing.
            bpy.data.meshes.remove(mesh)
            self.report({'ERROR'},
                        "This block's footprint is {:.2f} × {:.2f} cells — each side "
                        "needs to be a whole number of cells so it snaps to the grid. "
                        "Resize it and try again."
                        .format(dx / constants.U, dy / constants.U))
            return {'CANCELLED'}

        # Wrap the clean mesh in an object and write it to its own .blend. The object is
        # never linked to a collection, so it stays out of the user's scene entirely.
        obj = bpy.data.objects.new(type_id, mesh)
        library.write_custom_block(obj, type_id)

        # Tidy the temp datablocks out of this session so the live file is unchanged.
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)

        # Record the pointer in prefs and persist, so the block is a button next session.
        item = prefs_block.custom_blocks.add()
        item.name = name
        item.type_id = type_id
        bpy.ops.wm.save_userpref()

        self.report({'INFO'},
                    "Added block '{}' ({}×{} cells) — it's now a button in the Blocks "
                    "panel. Studs and height are up to you; Blender Blocks only checks the "
                    "footprint.".format(name, cells_x, cells_y))
        return {'FINISHED'}


class BLENDER_BLOCKS_OT_remove_block(bpy.types.Operator):
    """Remove one of your custom blocks from the library, deleting its stored .blend.
    The built-in blocks can't be removed. Blocks you already placed in the scene stay
    — they're normal mesh objects."""
    bl_idname = "blender_blocks.remove_block"
    bl_label = "Remove block"
    bl_description = "Remove this custom block from your library"
    bl_options = {'REGISTER'}   # preferences aren't part of Blender's undo stack

    type_id: bpy.props.StringProperty()

    def execute(self, context):
        prefs_block = prefs.addon_prefs(context)
        if prefs_block is None:
            self.report({'ERROR'}, prefs.BLOCKS_DISABLED_MSG)
            return {'CANCELLED'}

        coll = prefs_block.custom_blocks
        # CollectionProperty removes by index, not by id, so find the index first.
        index = next((i for i, it in enumerate(coll) if it.type_id == self.type_id), -1)
        if index < 0:
            self.report({'ERROR'}, "No custom block called '{}'.".format(self.type_id))
            return {'CANCELLED'}

        label = coll[index].name
        coll.remove(index)
        # Drop the geometry file too, so removal is complete (tolerates a missing file).
        library.delete_custom_block(self.type_id)
        bpy.ops.wm.save_userpref()
        self.report({'INFO'}, "Removed block '{}'.".format(label))
        return {'FINISHED'}


def _get_or_create_material(name, rgb, roughness, opacity, transmission):
    """Return the shared 'BlenderBlocks_<name>' material, creating it once if needed.
    One material per name, reused across every block that uses it.

    Principled BSDF only (no custom node graph). bpy note: modern materials are
    defined by their node tree, so we set use_nodes=True and edit the Principled
    node — never use_nodes=False, which gives flat viewport-only color and breaks
    the BSDF the look depends on.
    """
    mat_name = constants.MATERIAL_PREFIX + name
    mat = bpy.data.materials.get(mat_name)
    if mat is not None:
        return mat

    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    # Grab the Principled node by type, not by name — the label can be localised
    # or renamed, but the type is stable.
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Alpha"].default_value = opacity
    # Subsurface input was renamed to "Subsurface Weight" in Blender 4.x; guard the
    # set so a version mismatch degrades gracefully instead of raising KeyError.
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = constants.MATERIAL_SUBSURFACE
    # Transmission ("Clear") makes a block see-through like glass. Also renamed to
    # "Transmission Weight" in Blender 4.x; guard it the same way.
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission

    # bpy gotcha: alpha/transmission only show as see-through in EEVEE if the
    # material's render method allows blending. Blender 4.2 EEVEE Next uses
    # `surface_render_method` ('BLENDED'); older EEVEE used `blend_method` ('BLEND').
    # Cycles ignores both and is always correct. Set whichever this build has.
    if opacity < 1.0 or transmission > 0.0:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = 'BLENDED'
        elif hasattr(mat, "blend_method"):
            mat.blend_method = 'BLEND'

    # So the look is visible in Solid shading too (BSDF inputs only show in Material
    # Preview / Rendered). Alpha here drives the Solid-view opacity.
    mat.diffuse_color = (rgb[0], rgb[1], rgb[2], opacity)
    return mat


class BLENDER_BLOCKS_OT_apply_material(bpy.types.Operator):
    """Give the selected blocks a material — a preset or one of your custom ones —
    as a real Blender material."""
    bl_idname = "blender_blocks.apply_material"
    bl_label = "Apply material"
    bl_description = "Give the selected blocks this material"
    bl_options = {'REGISTER', 'UNDO'}

    # Which material to apply, by name. The swatch button sets this; one operator,
    # one action.
    material_name: bpy.props.StringProperty()

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets:
            self.report({'ERROR'}, "Select one or more blocks first, then pick a material.")
            return {'CANCELLED'}

        # Look the recipe up by name so prefs.iter_materials stays the one source of
        # truth (presets + custom). Shouldn't be missing when called from the UI.
        spec = prefs.get_material_spec(context, self.material_name)
        if spec is None:
            self.report({'ERROR'}, "Unknown material '{}'.".format(self.material_name))
            return {'CANCELLED'}

        mat = _get_or_create_material(
            spec["name"], spec["color"], spec["roughness"],
            spec["opacity"], spec["transmission"],
        )

        # Assign to each block's mesh data. Each placed block is its own append, so
        # meshes aren't shared — data-level assignment is the standard, safe choice.
        for obj in targets:
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

        message = ("Applied '{}' to {} block(s). Find it in the Properties panel "
                   "→ Material tab.").format(mat.name, len(targets))
        self.report({'INFO'}, message)
        return {'FINISHED'}


# Finish-preset lookups, built once from the constants table.
#   _FINISH_ENUM_ITEMS: EnumProperty items (id, label, description).
#   _FINISH_LOOKUP:     id -> (roughness, opacity, transmission).
# bpy gotcha: EnumProperty items given as a static tuple keep their strings alive;
# a *callback* that returns freshly-built strings can have them garbage-collected
# and show garbled labels, so prefer the static list when the choices are fixed.
_FINISH_ENUM_ITEMS = tuple(
    (pid, label, "{} finish".format(label))
    for pid, label, _r, _o, _t in constants.FINISH_PRESETS
)
_FINISH_LOOKUP = {pid: (r, o, t) for pid, _label, r, o, t in constants.FINISH_PRESETS}


class BLENDER_BLOCKS_OT_add_material(bpy.types.Operator):
    """Make a custom material (name + color + finish) and save it to your library,
    so it shows up as a swatch in every file. The finish preset sets the
    roughness/opacity/transmission; to capture a fully custom look, build a material
    in the shader editor and use 'Add from material' instead."""
    bl_idname = "blender_blocks.add_material"
    bl_label = "Add material"
    bl_description = "Create a custom material and add it to your library"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(name="Name", default="My material")
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', size=3, min=0.0, max=1.0,
        default=(0.8, 0.8, 0.8),
    )
    finish: bpy.props.EnumProperty(
        name="Finish", items=_FINISH_ENUM_ITEMS, default=_FINISH_ENUM_ITEMS[0][0],
    )

    def invoke(self, context, event):
        # invoke_props_dialog pops a small modal dialog (auto-drawing our props:
        # name, color, finish) before execute() runs.
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = self.name.strip()
        if not name:
            self.report({'ERROR'}, "Give the material a name first.")
            return {'CANCELLED'}
        if prefs.material_name_exists(context, name):
            self.report({'ERROR'},
                        "A material called '{}' already exists — pick another name."
                        .format(name))
            return {'CANCELLED'}

        # The finish preset fully determines the look (no fine-tune sliders).
        roughness, opacity, transmission = _FINISH_LOOKUP[self.finish]

        prefs_block = prefs.addon_prefs(context)
        if prefs_block is None:
            self.report({'ERROR'}, prefs.PREFS_DISABLED_MSG)
            return {'CANCELLED'}

        item = prefs_block.custom_materials.add()
        item.name = name
        item.color = self.color
        item.roughness = roughness
        item.opacity = opacity
        item.transmission = transmission

        # Persist to disk so the material is there next session, even if Blender's
        # "Auto-Save Preferences" is off. This is the one place Blender Blocks writes the
        # global user preferences.
        bpy.ops.wm.save_userpref()

        note = ""
        if transmission > 0.0:
            note = (" Heads-up: transmission only looks see-through in EEVEE with "
                    "Raytracing / Screen-Space Refraction on — it always works in "
                    "Cycles.")
        self.report({'INFO'}, "Added material '{}'.{}".format(name, note))
        return {'FINISHED'}


class BLENDER_BLOCKS_OT_remove_material(bpy.types.Operator):
    """Remove one of your custom materials from the library. The built-in color
    presets can't be removed."""
    bl_idname = "blender_blocks.remove_material"
    bl_label = "Remove material"
    bl_description = "Remove this custom material from your library"
    bl_options = {'REGISTER'}   # preferences aren't part of Blender's undo stack

    name: bpy.props.StringProperty()

    def execute(self, context):
        prefs_block = prefs.addon_prefs(context)
        if prefs_block is None:
            self.report({'ERROR'}, prefs.PREFS_DISABLED_MSG)
            return {'CANCELLED'}
        coll = prefs_block.custom_materials
        # CollectionProperty removes by index, not by name, so find the index first.
        index = next((i for i, it in enumerate(coll) if it.name == self.name), -1)
        if index < 0:
            self.report({'ERROR'}, "No custom material called '{}'.".format(self.name))
            return {'CANCELLED'}

        coll.remove(index)
        bpy.ops.wm.save_userpref()
        self.report({'INFO'}, "Removed material '{}'.".format(self.name))
        return {'FINISHED'}


def _read_principled(mat):
    """Read (rgb, roughness, opacity, transmission) off a material's Principled
    BSDF, or None if it hasn't got one. Reads the node inputs' default_value, so a
    color driven by a texture node comes back as whatever constant sits behind it."""
    if not mat.use_nodes or mat.node_tree is None:
        return None
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return None
    base = bsdf.inputs["Base Color"].default_value
    transmission = (bsdf.inputs["Transmission Weight"].default_value
                    if "Transmission Weight" in bsdf.inputs else 0.0)
    return ((base[0], base[1], base[2]),
            bsdf.inputs["Roughness"].default_value,
            bsdf.inputs["Alpha"].default_value,
            transmission)


def _on_source_change(self, context):
    """When the source material is picked, default the library name to it (minus our
    BlenderBlocks_ prefix) — but only if the user hasn't typed their own name yet."""
    mat = bpy.data.materials.get(self.source_name)
    if mat is not None and not self.name:
        n = mat.name
        if n.startswith(constants.MATERIAL_PREFIX):
            n = n[len(constants.MATERIAL_PREFIX):]
        self.name = n


class BLENDER_BLOCKS_OT_add_material_from_existing(bpy.types.Operator):
    """Add one of this file's existing materials to your Blender Blocks library by reading
    its Principled BSDF (color, roughness, opacity, transmission). The handy way to
    capture a fully custom look: build it in the shader editor, then grab it here."""
    bl_idname = "blender_blocks.add_material_from_existing"
    bl_label = "Add from material"
    bl_description = "Copy an existing material in this file into your Blender Blocks library"
    bl_options = {'REGISTER', 'UNDO'}

    source_name: bpy.props.StringProperty(name="Material", update=_on_source_change)
    name: bpy.props.StringProperty(name="Save as", default="")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        # prop_search gives a searchable dropdown of every material in the .blend.
        layout.prop_search(self, "source_name", bpy.data, "materials", text="Material")
        layout.prop(self, "name")

    def execute(self, context):
        mat = bpy.data.materials.get(self.source_name)
        if mat is None:
            self.report({'ERROR'}, "Pick an existing material to copy first.")
            return {'CANCELLED'}

        read = _read_principled(mat)
        if read is None:
            self.report({'ERROR'},
                        "'{}' has no Principled BSDF I can read.".format(mat.name))
            return {'CANCELLED'}
        rgb, roughness, opacity, transmission = read

        name = self.name.strip()
        if not name:
            # Fall back to the source name, minus our prefix.
            name = mat.name
            if name.startswith(constants.MATERIAL_PREFIX):
                name = name[len(constants.MATERIAL_PREFIX):]
        if prefs.material_name_exists(context, name):
            self.report({'ERROR'},
                        "A material called '{}' already exists — pick another name."
                        .format(name))
            return {'CANCELLED'}

        prefs_block = prefs.addon_prefs(context)
        if prefs_block is None:
            self.report({'ERROR'}, prefs.PREFS_DISABLED_MSG)
            return {'CANCELLED'}

        item = prefs_block.custom_materials.add()
        item.name = name
        item.color = rgb
        item.roughness = roughness
        item.opacity = opacity
        item.transmission = transmission
        bpy.ops.wm.save_userpref()

        self.report({'INFO'}, "Added material '{}' from '{}'.".format(name, mat.name))
        return {'FINISHED'}


class BLENDER_BLOCKS_OT_nudge(bpy.types.Operator):
    """Move the selected blocks by whole grid cells, so they always stay aligned
    to the grid — unlike a free G-drag, which can drift to a fraction of a cell."""
    bl_idname = "blender_blocks.nudge"
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
        self.report({'INFO'}, message)
        return {'FINISHED'}


def _snap_to_grid(obj, context):
    """Shift `obj` so the minimum corner of its footprint lands on the grid.

    Used after rotating: a 90° turn can leave odd-dimension blocks (e.g. 1x3)
    half a cell off the lattice. We snap the world-space bounding-box min corner
    to the nearest cell, which nudges the block back onto the grid by at most
    half a cell.

    bpy gotcha: obj.matrix_world is recomputed lazily, so after we change
    location/rotation it's stale until the view layer updates. Force that update
    before reading bound_box corners, or we'd snap using the *old* transform.
    """
    context.view_layer.update()
    mw = obj.matrix_world
    corners = [mw @ Vector(c) for c in obj.bound_box]
    min_x = min(v.x for v in corners)
    min_y = min(v.y for v in corners)
    min_z = min(v.z for v in corners)
    obj.location.x += round(min_x / constants.U) * constants.U - min_x
    obj.location.y += round(min_y / constants.U) * constants.U - min_y
    obj.location.z += round(min_z / constants.H) * constants.H - min_z


def _rotate_obj_about_center(obj, steps, context):
    """Turn `obj` `steps`×90° about Z, pivoting on its own footprint center so it spins
    in place, then re-snap to the grid. Shared by the rotate operator and the ghost
    builder (a plan's '2x4' is the library '4x2' turned 90°)."""
    angle = steps * (math.pi / 2)
    rot = Matrix.Rotation(angle, 4, 'Z')

    # Pivot point = the block's footprint center in world space. bound_box is 8 local
    # corners; averaging them gives the center regardless of where the origin sits
    # (ours is at the bottom -X/-Y corner).
    local_center = sum((Vector(c) for c in obj.bound_box), Vector()) / 8
    pivot = obj.matrix_world @ local_center

    # Rigid rotation of the whole object about `pivot`: every point x maps to
    # pivot + rot·(x − pivot). Applying that to the origin gives the new location;
    # composing rot onto the existing orientation turns the block. Doing the math with
    # mathutils (not by re-reading matrix_world) means we don't depend on a depsgraph
    # refresh mid-loop.
    obj.location = pivot + rot @ (obj.location - pivot)
    obj.rotation_euler.rotate_axis('Z', angle)

    # Re-snap so odd-dimension blocks land cleanly back on the lattice.
    _snap_to_grid(obj, context)


class BLENDER_BLOCKS_OT_rotate(bpy.types.Operator):
    """Turn the selected blocks 90° around the up (Z) axis, pivoting about each
    block's own footprint center so it spins in place and stays on the grid."""
    bl_idname = "blender_blocks.rotate"
    bl_label = "Rotate block"
    bl_description = "Turn the selected blocks 90° around the up axis"
    bl_options = {'REGISTER', 'UNDO'}

    # +1 = one 90° step counter-clockwise (seen from above), -1 = clockwise. A
    # panel button sets this; one operator, parameterised — no branching.
    steps: bpy.props.IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets:
            self.report({'ERROR'}, "Select a block to rotate.")
            return {'CANCELLED'}

        for obj in targets:
            _rotate_obj_about_center(obj, self.steps, context)

        direction = "left" if self.steps > 0 else "right"
        message = ("Turned {} block(s) 90° {} — still on the grid."
                   .format(len(targets), direction))
        self.report({'INFO'}, message)
        return {'FINISHED'}


class BLENDER_BLOCKS_OT_delete(bpy.types.Operator):
    """Remove the selected blocks from the scene entirely."""
    bl_idname = "blender_blocks.delete"
    bl_label = "Delete block"
    bl_description = "Remove the selected blocks from the scene"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets:
            self.report({'ERROR'}, "Select a block to delete.")
            return {'CANCELLED'}

        count = len(targets)
        # bpy note: bpy.data.objects.remove(do_unlink=True) unlinks the object from
        # every collection and deletes the object data-block in one call — cleaner
        # and more predictable than bpy.ops.object.delete(), which depends on the
        # right context override. The block's mesh is left as 0-user "orphan data"
        # (normal Blender behaviour — it's purged on save or via Outliner cleanup).
        for obj in targets:
            bpy.data.objects.remove(obj, do_unlink=True)

        message = "Deleted {} block(s).".format(count)
        self.report({'INFO'}, message)
        return {'FINISHED'}


# --- Follow-a-manual driver: ghost hint + navigation operators ---------------
# The plan/data helpers live in driver.py; the bits that need the material + rotate
# helpers above (ghost rendering) live here.

def _ghost_material():
    """The shared translucent 'BlenderBlocks_Ghost' material for hint previews."""
    return _get_or_create_material(
        constants.GHOST_MATERIAL, constants.GHOST_COLOR,
        constants.MATERIAL_ROUGHNESS, constants.GHOST_OPACITY, 0.0,
    )


def _clear_ghosts(context):
    """Remove the ghost hint: delete its objects and the throwaway collection. The
    orphaned meshes are normal Blender behaviour (purged on save / Outliner cleanup)."""
    coll = bpy.data.collections.get(constants.GHOST_COLLECTION)
    if coll is None:
        return
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(coll)


def _place_min_corner(obj, target, context):
    """Shift `obj` so its world bounding-box min (-X/-Y/-Z) corner sits at world `target`.

    For a ghost we rotate first (a plan '2x4' is the library '4x2' turned 90°), THEN anchor
    by the min corner — because the plan's `cell` is the bottom -X/-Y corner of the
    *as-placed* footprint, which a rotate-about-center wouldn't preserve. bpy gotcha:
    matrix_world is lazy, so update the view layer before reading bound_box."""
    context.view_layer.update()
    mw = obj.matrix_world
    corners = [mw @ Vector(c) for c in obj.bound_box]
    obj.location.x += target[0] - min(v.x for v in corners)
    obj.location.y += target[1] - min(v.y for v in corners)
    obj.location.z += target[2] - min(v.z for v in corners)


def _build_ghosts(context, step):
    """Show translucent preview copies of `step`'s blocks at their target cells, so you
    can see where this step goes. Real appended objects (glass-box) — deliberately NOT a
    GPU draw_handler overlay, which the project dropped as too fragile. Returns the count
    placed."""
    _clear_ghosts(context)
    blocks = step.get("add", [])
    if not blocks:
        return 0

    coll = bpy.data.collections.new(constants.GHOST_COLLECTION)
    context.scene.collection.children.link(coll)
    mat = _ghost_material()

    placed = 0
    for block in blocks:
        type_id, rot_steps = driver.ghost_spec(block)
        try:
            obj = library.append_block(type_id)
        except (FileNotFoundError, ValueError):
            # A block whose library object is missing just doesn't get a ghost — the
            # hint is best-effort, never a hard error.
            continue
        coll.objects.link(obj)
        # Rotate first (if the as-placed footprint is the library block turned 90°), then
        # anchor the min corner exactly on the plan's target cell.
        if rot_steps:
            obj.rotation_euler.rotate_axis('Z', rot_steps * (math.pi / 2))
        gx, gy, gz = block["cell"]
        _place_min_corner(obj, (gx * constants.U, gy * constants.U, gz * constants.H), context)
        # Overwrite the appended block's material slot with the ghost material.
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        obj.name = "Ghost_{}".format(type_id)
        obj.show_in_front = True   # draw over the solid build so the hint reads
        obj.hide_select = True     # don't let a ghost steal clicks from the real block
        placed += 1
    return placed


class BLENDER_BLOCKS_OT_driver_load(bpy.types.Operator):
    """Open a build-plan JSON and follow it step by step. Pre-creates one collection per
    bag under 'Blender Blocks Build'; blocks you place are sorted into the current bag."""
    bl_idname = "blender_blocks.driver_load"
    bl_label = "Load build plan"
    bl_description = "Open a build-plan JSON and follow it step by step"
    bl_options = {'REGISTER'}   # navigation/state, not part of Blender's modeling undo

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        # fileselect_add pops Blender's file browser; it re-runs execute() on confirm
        # with self.filepath set.
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            plan = driver.load_plan(self.filepath)
        except (ValueError, OSError) as e:
            self.report({'ERROR'}, "Couldn't load that build plan: {}".format(e))
            return {'CANCELLED'}

        driver.invalidate_cache(self.filepath)   # force a fresh read on the next get_plan
        state = context.scene.blender_blocks_driver
        state.plan_filepath = self.filepath
        state.model_name = (plan.get("model") or {}).get("name", "Untitled")
        state.global_index = 0
        state.checked_steps = ""
        state.show_ghost = False
        _clear_ghosts(context)

        # Pre-create every bag collection so the structure shows in the Outliner now,
        # then make the first bag active so hand-placed blocks land there.
        bags = plan.get("bags", [])
        for bag in bags:
            driver.ensure_bag_collection(context, bag.get("name", "Bag"))
        if bags:
            driver.set_active_bag(context, bags[0].get("name", "Bag"))

        self.report({'INFO'},
                    "Loaded '{}' — {} step(s) in {} bag(s). Build each step by hand; "
                    "tick it off as you go.".format(
                        state.model_name, driver.step_count(plan), len(bags)))
        return {'FINISHED'}


class BLENDER_BLOCKS_OT_driver_goto(bpy.types.Operator):
    """Move to another step. One parameterised operator: Prev/Next use `delta`, a jump
    uses `absolute` (>= 0)."""
    bl_idname = "blender_blocks.driver_goto"
    bl_label = "Go to step"
    bl_description = "Move to another step in the manual"
    bl_options = {'REGISTER'}

    delta: bpy.props.IntProperty(default=0)
    absolute: bpy.props.IntProperty(default=-1)   # -1 = use delta; >= 0 = jump there

    def execute(self, context):
        state = context.scene.blender_blocks_driver
        plan = driver.get_plan(state.plan_filepath)
        if plan is None:
            self.report({'ERROR'}, "Load a build plan first.")
            return {'CANCELLED'}

        n = driver.step_count(plan)
        target = self.absolute if self.absolute >= 0 else state.global_index + self.delta
        target = max(0, min(n - 1, target))
        state.global_index = target

        _bi, _si, bag_name, step = driver.locate(plan, target)
        if bag_name:
            driver.set_active_bag(context, bag_name)
        # Keep the ghost in step with where we are, if it's showing.
        if state.show_ghost:
            _build_ghosts(context, step)
        return {'FINISHED'}


class BLENDER_BLOCKS_OT_driver_toggle_check(bpy.types.Operator):
    """Tick a step off (or back on) — honor-system, no scene-checking. Defaults to the
    current step."""
    bl_idname = "blender_blocks.driver_toggle_check"
    bl_label = "Mark step done"
    bl_description = "Tick this step off as done (honor system)"
    bl_options = {'REGISTER'}

    index: bpy.props.IntProperty(default=-1)   # -1 = the current step

    def execute(self, context):
        state = context.scene.blender_blocks_driver
        idx = self.index if self.index >= 0 else state.global_index
        driver.toggle_checked(state, idx)
        return {'FINISHED'}


class BLENDER_BLOCKS_OT_driver_toggle_ghost(bpy.types.Operator):
    """Show or hide the 👻 ghost hint — translucent preview copies of the current step's
    blocks at their target cells, for when you're stuck."""
    bl_idname = "blender_blocks.driver_toggle_ghost"
    bl_label = "Ghost hint"
    bl_description = "Show translucent previews of this step's blocks where they go"
    bl_options = {'REGISTER'}

    def execute(self, context):
        state = context.scene.blender_blocks_driver
        plan = driver.get_plan(state.plan_filepath)
        if plan is None:
            self.report({'ERROR'}, "Load a build plan first.")
            return {'CANCELLED'}

        state.show_ghost = not state.show_ghost
        if state.show_ghost:
            _bi, _si, _bag, step = driver.locate(plan, state.global_index)
            count = _build_ghosts(context, step)
            self.report({'INFO'},
                        "Ghost hint on — {} preview piece(s). They're not part of your "
                        "build; toggle off to clear.".format(count))
        else:
            _clear_ghosts(context)
            self.report({'INFO'}, "Ghost hint off.")
        return {'FINISHED'}


class BLENDER_BLOCKS_OT_driver_clear(bpy.types.Operator):
    """Close the manual: clear the current-step/checkoff state and any ghost hint. The
    bag collections and the blocks you built stay — they're your scene."""
    bl_idname = "blender_blocks.driver_clear"
    bl_label = "Close manual"
    bl_description = "Stop following the manual (keeps your built blocks and bags)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        _clear_ghosts(context)
        state = context.scene.blender_blocks_driver
        state.plan_filepath = ""
        state.model_name = ""
        state.global_index = 0
        state.checked_steps = ""
        state.show_ghost = False
        self.report({'INFO'}, "Closed the manual. Your blocks and bags are untouched.")
        return {'FINISHED'}


# Each module exposes a `classes` tuple; __init__.py collects them for
# registration. Order matters: classes a panel references must register first,
# which is why operators register before panels.
classes = (
    BLENDER_BLOCKS_OT_add_block,
    BLENDER_BLOCKS_OT_add_block_from_selection,
    BLENDER_BLOCKS_OT_remove_block,
    BLENDER_BLOCKS_OT_apply_material,
    BLENDER_BLOCKS_OT_add_material,
    BLENDER_BLOCKS_OT_add_material_from_existing,
    BLENDER_BLOCKS_OT_remove_material,
    BLENDER_BLOCKS_OT_nudge,
    BLENDER_BLOCKS_OT_rotate,
    BLENDER_BLOCKS_OT_delete,
    BLENDER_BLOCKS_OT_driver_load,
    BLENDER_BLOCKS_OT_driver_goto,
    BLENDER_BLOCKS_OT_driver_toggle_check,
    BLENDER_BLOCKS_OT_driver_toggle_ghost,
    BLENDER_BLOCKS_OT_driver_clear,
)
