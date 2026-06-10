# Blender Blocks — Blender Add-on Project Brief

## Why this exists

Building with snap-together blocks in Blender is fun. Tedious, but fun — and weirdly
therapeutic. Blender Blocks is a personal toy that takes that pastime and removes the
tedium: pick a block, drop it on a grid, snap more next to it, color them in.

It is built for my own use. There's no audience to teach and no learning curve to
flatten. The one thing it must never do is trap what I make: every action leaves
behind a real, editable Blender scene I can keep tinkering with by hand.

## Core design principles (in priority order)

1. **Glass-box, not black-box.** Placed blocks are normal mesh objects with normal
   materials in a normal collection. No custom node graphs, no hidden state, no
   proprietary data that breaks when the add-on is disabled. If I uninstall Blender Blocks
   tomorrow, the scene still works — and at any point I can drop the toy and keep
   editing the build by hand.
2. **Stay on the grid.** Everything snaps. A build should always be cleanly aligned
   without fighting the viewport.
3. **Keep it small.** Add a feature when it makes building more fun, not to chase
   completeness. The "Not chasing these" list below is the focus boundary.
4. **Failure mode = friendly.** Errors never expose Python tracebacks. Catch and
   surface plain-English messages.

## Block library

~22 blocks, already modeled in Blender. Key facts:

- **All scales are applied** (scale = 1,1,1 on every object).
- **Grid unit:** every block aligns to a grid where **one cell = 1.0 Blender unit**.
  The blocks are authored at 2.0 BU/cell; `build_library.py` halves them so a cell
  equals one native Blender unit. That way Blender's default grid and increment-snap
  (which step by 1.0) line up with cells, and a block at cell `(gx, gy, gz)` sits at
  world `(gx, gy, gz)`. *(History: originally specced as 2mm-in-meters; on 2026-06-07
  switched to the blocks' native 2.0-BU scale, then halved to 1.0 BU/cell — far more
  viewable in Blender's default viewport.)*
- **Block list:** see `blender_blocks/constants.py` → `BLOCK_TYPES` for the live catalogue
  (1×1, 1×1 round, 2×1, 2×2, 3×1, 3×2, 4×1, 4×2, 4×2 smooth, 6×1, 8×2, Step, L-block,
  T-block, 10×2, 10×4, 10×8, 10×10, 20×10, 20×20).
- **Not real LEGO proportions.** Custom geometry. Refer to them as "blocks" or "snap
  blocks", never "LEGO" or "bricks."

### Custom blocks (added 2026-06-07)

Beyond the built-in catalogue, blocks can be captured **in Blender** from any selection:
the **Add block from selection…** button (Blocks panel) takes the active mesh object,
makes a clean copy (bakes in rotation/scale, re-origins to the bottom -X/-Y corner,
strips materials — the original object is left untouched), and saves it. Removal is in
the same panel and in Add-on prefs.

- **Storage:** one `.blend` per custom block under Blender's per-user CONFIG dir
  (`config/blender_blocks/custom_blocks/<type_id>.blend`), *outside* the package — so an
  add-on reinstall never wipes them. A lightweight pointer (display name + slug
  `type_id`) lives in `AddonPreferences.custom_blocks`; `prefs.iter_blocks()` is the one
  source of truth the panel reads (built-ins, then customs). This mirrors how custom
  *materials* are stored.
- **Validation:** the X/Y footprint must be a whole number of cells (else it's refused
  with a friendly message — we don't silently round). Z is not checked against whole
  cells, since studs make a block stand a little over 1.0. Stud/height alignment with
  other blocks is the modeler's responsibility — glass-box, edit by hand as needed.
- **Glass-box still holds:** a placed custom block is an ordinary appended mesh in
  `Blender Blocks Build`, the stored `.blend` is a normal file, and the prefs entry is only a
  pointer.

### Pre-flight checklist for the blocks

**Source file specifics:**

- Master file: `source_blocks/all_blocks.blend` (single .blend containing all blocks).
- All blocks live in a Blender collection named `"blocks"` inside that file. Iterate via
  `bpy.data.collections["blocks"].objects` — do not iterate the whole scene.
- Blocks are currently hidden in the viewport. Fine; the cleanup utility doesn't care
  about visibility state.
- Each block is a single mesh object (no multi-object blocks).
- Block names are meaningful (e.g. `1x1`, `2x4`, `T_Block`) — preserve these as the
  block-type identifier when placed blocks are named `Block_<type>.<counter>`.

**Important: never modify the source file directly.** The cleanup utility reads from
`source_blocks/all_blocks.blend` and writes to `blender_blocks/blender_blocks_library.blend`. The
source is the master copy and is sacred.

The cleanup utility (run inside Blender's scripting tab — `bpy` is only available there):

1. Loads `source_blocks/all_blocks.blend` via `bpy.data.libraries.load()`.
2. **Verifies the origin convention.** If any block deviates, *report it via
   print/console* rather than silently fixing — I want visibility into discrepancies.
   *(2026-06-07: the audit found origins consistent in Z but scattered in X/Y. We
   re-origin all blocks to the **bottom -X/-Y corner of the footprint** in
   `build_library.py` — report first via `audit_blocks.py`, then re-origin the library
   copy only, never the source. Corner — not center — because center's meaning flips
   with footprint parity (a stud for odd footprints, a valley for even), which puts
   odd/even blocks on half-cell-offset lattices and makes them overlap. A corner anchor
   is parity-independent: a W×D block at grid cell `(gx, gy)` fills cells
   `[gx..gx+W)`, studs always co-align.)*
3. Confirms applied scale on each object (scale = 1,1,1). Report any deviations.
4. Confirms dimensions are sensible multiples of the grid unit. Report any block whose
   dimensions don't cleanly divide.
5. Strips any embedded materials (the color system applies materials at runtime).
6. Writes the cleaned blocks into `blender_blocks/blender_blocks_library.blend` as a fresh asset
   library.

The utility prints a clear report at the end (blocks processed, origin/scale/dimension
results, materials stripped, output path).

## Architecture

### Grid system

Constants live in `blender_blocks/constants.py`:

```python
U = 1.0  # grid cell size on X and Y, in Blender units (one cell = 1.0 BU)
H = 1.0  # block body height on Z = one cell. Studs add a little on top.
```

All placement coordinates are integer multiples of U on X and Y, and integer multiples
of H on Z. Internally, store block positions as integer grid coordinates `(gx, gy, gz)`
and convert to world coordinates only when placing.

### Block storage (bundled assets)

Ship the cleaned blocks in `blender_blocks_library.blend` inside the addon folder. Load on
demand with `bpy.data.libraries.load()` — append (not link) so each placed block is its
own editable copy of the mesh data.

### Placement flow

1. Click a block button in the Blender Blocks side panel (N-panel, category "Blender Blocks").
2. The add-on appends that block from the library at the 3D cursor, snapped to the
   nearest grid cell.
3. The new block is auto-selected, and grid snapping is enabled so a follow-up G-drag
   stays on the grid (`tool_settings.use_snap = True`, increment snap on absolute cell
   lines).
4. A status-bar message names the real object and where it landed.

For reliable nudging, the **Move** panel shifts the selection by exactly one whole cell
per click (a free G-drag can drift to a fraction of a cell when zoomed in). There are
deliberately no arrow-key shortcuts — Blender binds the arrow keys to frame stepping,
and fighting that keymap causes more trouble than it's worth.

**Deferred:**
- True click-and-drag from the panel into the viewport (Blender doesn't natively
  support this; it's hacky and slow to build).
- Auto-stacking via raycast from cursor.
- Multi-select duplication / arrays.

### Naming convention for placed blocks

`Block_<type>.<counter>` — e.g. `Block_2x4.001`, `Block_T.001`. This is what shows in
the Outliner. Keep it readable.

All placed blocks go into a collection called `Blender Blocks Build` — clean grouping in the
Outliner.

### Color system

A "Colors" panel section with preset swatches (see `constants.COLOR_PRESETS`: white,
black, red, orange, yellow, green, blue, gray). Clicking a swatch with blocks selected:

1. Creates (or reuses) a material named `BlenderBlocks_<colorname>` with that base color, a
   plastic-ish roughness (~0.4), and a touch of subsurface.
2. Assigns it to the selected blocks.
3. Shows a status message naming the material and where to find it.

Materials are real Blender materials — Principled BSDF only, no custom shader nodes.

## File structure

```
blender_blocks/
├── __init__.py          # Addon registration, bl_info
├── constants.py         # U, H, color presets, block catalogue
├── operators.py         # bpy.types.Operator subclasses (add_block, apply_color, nudge, rotate, delete)
├── panels.py            # bpy.types.Panel subclasses (main panel + subpanels)
├── library.py           # Block loading from blender_blocks_library.blend
└── blender_blocks_library.blend  # Bundled block assets
```

## Blender API concepts the code uses

(Reference — the bpy areas this touches.)

- `bpy.types.Operator` — every user action is an operator.
- `bpy.types.Panel` — the side-panel UI.
- `bpy.props` — operator properties (which block, which color, nudge axis, etc.).
- `bpy.data.libraries.load()` — appending blocks from the bundled .blend.
- `bpy.context.scene.tool_settings` — for forcing grid snap on.
- `bpy.types.Collection` — for the Blender Blocks Build collection.
- Standard `register()` / `unregister()` pattern in `__init__.py`.

## Compatibility target

- Blender 4.2+ (current LTS). No backward compat to 3.x.
- Cross-platform (Windows, Mac, Linux) — bpy handles this; just don't hardcode path
  separators.

## Build order

1. Block-cleanup utility (origin verification, scale check, material stripping,
   dimension audit) targeting `source_blocks/all_blocks.blend` →
   `blender_blocks/blender_blocks_library.blend`. Run it in Blender and read the report before
   proceeding.
2. Resolve any discrepancies the report flags.
3. Scaffold the addon folder with a working `bl_info` / `register()` / `unregister()`.
4. Panel UI (block buttons, color swatches, move/rotate/delete).
5. The "add block" operator with library loading.
6. Color system.
7. Move / rotate / delete operators.

## Not chasing these (for now)

- Custom textures
- Animation tools
- Export to LDraw or other formats
- Auto-stacking via raycast
- True drag-and-drop from panel to viewport
- Multi-block templates / saved builds
- Undo system beyond Blender's native undo

None of these are off-limits forever — they're just not what makes building more fun
right now. Add one if it does.

## Tone for in-app text

Friendly, plain English, never condescending, no Python jargon. Examples:

- ✅ "Added a 2×4 block — a normal mesh object in the 'Blender Blocks Build' collection."
- ❌ "Brick added successfully!"
- ❌ "Initialized bpy.types.Object with mesh data from library."

## When it's working

There's no stopwatch and no acceptance test. It works when building with it feels good —
fast to place, snap, move, and color, and the result is a real Blender scene worth
keeping. It's done when I stop wanting to change it.

## Legacy code (from an earlier attempt)

There was a partial version years ago under the working name "LEGO Toolkit" — a single
file (`legacy_addon.py`). Its useful patterns (the `register()`/`unregister()` +
`classes` list, the main-panel + subpanel structure via `bl_parent_id`, the
operator-per-action split, `bl_category` for the N-panel tab) were salvaged into the
current package. The dead `scene.my_tool` reference and all "LEGO" naming were dropped.
Nothing else remains to hunt for.
