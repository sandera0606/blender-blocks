# SnapBlock — Blender Add-on Project Brief

## Vision

A Blender add-on that gives intimidated adult beginners a friendly, snap-block-style entry point into Blender 3D. The user drops pre-made blocks into a scene, snaps them together on a grid, and colors them — while the add-on *quietly teaches them Blender along the way*.

This is **not** a walled-garden app inside Blender. It is **trainer wheels for Blender itself**. Every action should leave behind a real, editable Blender scene the user can graduate into.

## Target user

Adults who have heard Blender is powerful, tried it, and bounced off the learning curve. They want to make something fun in 90 seconds, not watch a 4-hour donut tutorial before placing their first cube.

## Core design principles (in priority order)

1. **Glass-box, not black-box.** Every snap-block action should expose the underlying Blender operation it performs (via tooltip, status bar message, or info panel). Example: when the user clicks a block in the panel, show *"Added mesh object 'Block_2x4.001' — view it in the Outliner (top-right)."*
2. **The scene must remain a valid Blender scene.** No custom node graphs, no hidden state, no proprietary data structures that break when the add-on is disabled. Placed blocks are normal mesh objects with normal materials. If the user uninstalls SnapBlock tomorrow, their scene still works.
3. **Ruthless v0.1 scope.** Ship a minimum interesting version before adding features. Custom block uploads, custom textures, animation helpers, export tools — all later.
4. **Failure mode = friendly.** Errors never expose Python tracebacks to the user. Catch and surface plain-English messages.

## Brick library (provided by user)

The user has already modeled ~22 blocks in Blender. Key facts:

- **All scales are applied** (scale = 1,1,1 on every object).
- **Grid unit:** every block aligns to a grid where **one cell = 2.0 Blender units** (the blocks' native modeling scale). A 1x1 block is 2.0 × 2.0 × 2.0 BU (body height; studs add ~0.5 BU on top). A 4x2 block is 4.0 × 8.0 × 2.0 BU. Etc. *(Originally specced as 2mm-in-meters; on 2026-06-07 we kept the blocks' native 2.0-BU scale instead — simpler and far more viewable in Blender's default viewport. See Grid system below.)*
- **Block list:** T-block, L-block, 20x20, 20x20 (variant), 10x10, 10x8, 10x4, 10x2, 8x2, 6x1, 4x2 smooth (no studs), 4x2, 4x2 (variant), 3x2, 3x1, 2x2, 2x2 (variant), 2x1 step, 2x1, 1x1 cylinder, 1x1.
- **Not real LEGO proportions.** Custom geometry, no trademark exposure. Refer to them as "blocks" or "snap blocks", never "LEGO" or "bricks."

### Pre-flight checklist for the user's blocks (handle this first)

**Source file specifics (provided by user):**

- Master file: `source_blocks/all_blocks.blend` (single .blend containing all blocks).
- All blocks live in a Blender collection named `"blocks"` inside that file. Iterate via `bpy.data.collections["blocks"].objects` — do not iterate the whole scene.
- Blocks are currently hidden in the viewport. This is fine; the cleanup utility doesn't care about visibility state.
- Each block is a single mesh object (no multi-object blocks).
- Block names are meaningful (e.g. `1x1`, `2x4`, `T_Block`) — preserve these as the block-type identifier when placed blocks are named `Block_<type>.<counter>`.
- Origin points are believed to be consistent across blocks. Verify during cleanup and report any outliers to the user rather than silently re-origining (they want to know about discrepancies).

**Important: never modify the source file directly.** The cleanup utility reads from `source_blocks/all_blocks.blend` and writes to `snapblock/snapblock_library.blend`. The source is the user's master copy and is sacred.

Before writing the addon logic, write a small utility script (to be run inside Blender's scripting tab — `bpy` is only available there, not from a terminal) that:

1. Loads `source_blocks/all_blocks.blend` via `bpy.data.libraries.load()`.
2. Iterates the `blocks` collection and **verifies origin convention**. If any block deviates, *report it to the user via print/console* rather than silently fixing — the user wants visibility into discrepancies. *(2026-06-07: the audit found origins consistent in Z but scattered in X/Y. We re-origin all blocks to the **bottom -X/-Y corner of the footprint** in `build_library.py` — report first via `audit_blocks.py`, then re-origin the library copy only, never the source. Corner — not center — because center's meaning flips with footprint parity (a stud for odd footprints, a valley for even), which puts odd/even blocks on half-cell-offset lattices and makes them overlap. A corner anchor is parity-independent: a W×D block at grid cell `(gx, gy)` fills cells `[gx..gx+W)`, studs always co-align.)*
3. Confirms applied scale on each object (scale = 1,1,1). Report any deviations.
4. Confirms dimensions are sensible multiples of the 2mm grid unit. Report any block whose dimensions don't cleanly divide.
5. Strips any embedded materials (the color system will apply materials at runtime).
6. Writes the cleaned blocks into `snapblock/snapblock_library.blend` as a fresh asset library.

The utility should produce a clear report at the end:

```
Cleanup report:
  ✓ 22 blocks processed
  ✓ All origins at bottom-center
  ✓ All scales applied
  ⚠ Block "T_Block" dimensions: 0.006 × 0.004 × 0.002m — non-standard depth, please verify
  ✓ Materials stripped
  ✓ Written to snapblock/snapblock_library.blend
```

## Architecture

### Grid system

Define constants at the top of the addon:

```python
U = 2.0  # grid cell size in Blender units (blocks' native scale; one cell = 2.0 BU)
H = 2.0  # block body height = one cell. Studs add ~0.5 BU on top and nest into the block above.
```

All placement coordinates are integer multiples of U on X and Y, and integer multiples of H on Z. Internally, store block positions as integer grid coordinates `(gx, gy, gz)` and convert to world coordinates only when placing.

### Block storage (bundled assets)

Ship the cleaned blocks in `snapblock_library.blend` inside the addon folder. Load on demand with `bpy.data.libraries.load()` — append (not link) so users get their own editable copy of the mesh data.

### Placement flow (v0.1 — keep it simple)

1. User clicks a block thumbnail in the SnapBlock side panel (N-panel, category "SnapBlock").
2. The add-on appends that block from the library at the location of the 3D cursor, snapped to the nearest grid cell.
3. The new block is auto-selected and the user can press G to nudge it, with grid snapping enabled (the add-on enforces `bpy.context.scene.tool_settings.use_snap = True` and snap increment = U).
4. A subtle status-bar message appears: *"Added Block_2x4 at (0, 0, 0). Press G to move, R to rotate."*

**Explicitly defer for later:**
- True click-and-drag from the panel into the viewport (Blender doesn't natively support this; it's hacky and slow to build).
- Auto-stacking via raycast from cursor.
- Multi-select duplication / arrays.

### Naming convention for placed blocks

`Block_<type>.<counter>` — e.g. `Block_2x4.001`, `Block_TBlock.001`. This is what the user sees in the Outliner. Make it readable; they will see it.

All placed blocks go into a collection called `SnapBlock Build` so the user understands the grouping concept (collections are a real Blender feature — surface it).

### Color system

A panel section called "Colors" with 6–8 preset swatches (white, black, red, blue, yellow, green, gray, plus one accent). Clicking a swatch with blocks selected:

1. Creates (or reuses) a material named `SnapBlock_<colorname>` with that base color and a sensible roughness (~0.4) and a touch of subsurface for plastic-ish feel.
2. Assigns it to the selected blocks.
3. Shows a status message: *"Applied material 'SnapBlock_Red' to 3 blocks. Materials live in the Properties panel → Material tab."*

Materials are real Blender materials. Don't use custom shader nodes for v0.1 — just Principled BSDF with adjusted values.

### "Reveal" feature (the trainer-wheels payoff)

A toggle button at the top of the panel: **"Show me what's really happening"**. When enabled:

- Tooltips on every panel button expand to include the Python operator they call.
- After every action, a small overlay appears in the viewport for ~3 seconds explaining the Blender concept involved.
- A "Concept Glossary" expandable section appears with plain-English definitions of: Object, Mesh, Material, Collection, Outliner, Properties Panel, Modifier, Origin Point.

This is the single most important feature. Do not cut it from v0.1.

## File structure

```
snapblock/
├── __init__.py          # Addon registration, bl_info
├── constants.py         # U, H, color presets, block list
├── operators.py         # bpy.types.Operator subclasses (add_block, apply_color, toggle_reveal)
├── panels.py            # bpy.types.Panel subclasses (main panel, color subpanel, reveal subpanel)
├── library.py           # Block loading from snapblock_library.blend
├── reveal.py            # Reveal-mode tooltip and overlay logic
├── snapblock_library.blend  # Bundled block assets
└── icons/               # Optional thumbnails for the block picker (use bpy.utils.previews)
```

## Blender API concepts the code needs to use

(For Claude Code's reference — these are the bpy areas you'll touch.)

- `bpy.types.Operator` — every user action is an operator.
- `bpy.types.Panel` — the side-panel UI.
- `bpy.props` — for user-facing properties (reveal mode toggle, selected color, etc.) stored on the scene.
- `bpy.data.libraries.load()` — appending blocks from the bundled .blend.
- `bpy.utils.previews` — for the block thumbnail picker.
- `bpy.context.scene.tool_settings` — for forcing grid snap on.
- `bpy.types.Collection` — for the SnapBlock Build collection.
- Standard `register()` / `unregister()` pattern in `__init__.py`.

## Compatibility target

- Blender 4.2+ (current LTS as of writing). Don't worry about backward compat to 3.x.
- Cross-platform (Windows, Mac, Linux) — bpy handles this; just don't hardcode path separators.

## What to build first (v0.1 milestone)

A working add-on that lets the user:

1. Enable SnapBlock from Preferences → Add-ons.
2. Open the N-panel and see the SnapBlock tab.
3. Click a block thumbnail — block appears at 3D cursor, snapped to grid.
4. Apply one of 6 colors to selected blocks.
5. Toggle "Show me what's really happening" and see real-Blender tooltips.

If a user can build a tiny house in 90 seconds with v0.1, the project works. Everything else is polish.

## Out of scope for v0.1 (explicitly)

- Custom block uploads
- Custom textures
- Animation tools
- Export to LDraw or other formats
- Auto-stacking via raycast
- True drag-and-drop from panel to viewport
- Multi-block templates / saved builds
- Undo system beyond Blender's native undo

## Tone for in-app text

Friendly, plain English, never condescending. The user is a smart adult who just hasn't learned Blender yet. Examples:

- ✅ "Added a 2x4 block. It's a regular Blender object — you can see it in the Outliner on the right."
- ❌ "Brick added successfully!"
- ❌ "Initialized bpy.types.Object with mesh data from library."

## First steps when you (Claude Code) start

1. Confirm you've read this brief and `legacy_addon.py`. Summarize the v0.1 scope back to the user before writing code.
2. Write the block-cleanup utility (origin verification, scale check, material stripping, dimension audit) targeting `source_blocks/all_blocks.blend` → `snapblock/snapblock_library.blend`. Have the user run it in Blender's scripting tab and share the report before proceeding.
3. Resolve any discrepancies the report flags (with the user's input).
4. Scaffold the addon folder with empty modules and a working `bl_info` / `register()` / `unregister()`, salvaging structure from `legacy_addon.py`.
5. Build the panel UI with hardcoded block names first — no library loading yet — just to confirm the panel renders.
6. Wire up the "add block" operator with library loading.
7. Add color system.
8. Add reveal mode.
9. Ship v0.1 and have the user test the 90-second-house benchmark.

## Legacy code (from user's earlier attempt)

The user wrote a partial version of this add-on a few years ago under the working name "LEGO Toolkit." A single file (`legacy_addon.py`) is the complete inheritance — there is **no missing PropertyGroup file or other source** to hunt for, even though the legacy code references `scene.my_tool`. That reference is dead and should be ignored.

**Salvage from the legacy code:**

- The overall `register()` / `unregister()` pattern with a `classes` list. Idiomatic and correct.
- The main-panel + subpanel structure using `bl_parent_id`. This is the right architecture for SnapBlock's UI — reuse it.
- The `row.template_ID(ob, "active_material", new="material.new")` idiom for material selection. This is a non-obvious bpy pattern; keep it for the materials section.
- The enable/disable column pattern based on whether an active material exists (`c1.enabled, c2.enabled = True, True` etc.). Good defensive UI; reuse the pattern for any button that needs an object selected.
- The operator-per-action split (separate `LEGO_OT_SetOpaque` and `LEGO_OT_SetClear` rather than one branching operator). Keep this style.
- `bl_category` on the main panel for the N-panel tab name. Just rename the value to `"SnapBlock"`.

**Fix or discard:**

- All references to "LEGO" — rename to "SnapBlock" everywhere (bl_info, class names, idnames, labels).
- `bl_category` on the subpanels — subpanels inherit the parent's category, so these lines do nothing. Remove.
- `"blender": (3, 0, 0)` — bump to `(4, 2, 0)`.
- `mat.use_nodes = False` in the operators — **remove this line entirely**. Modern Blender materials are defined by their node tree; disabling nodes gives flat viewport-only color and breaks the Principled BSDF setup SnapBlock needs.
- `mat.blend_method = 'BLEND'` for transparency — defer transparent materials to a later version. v0.1 is opaque-only with proper Principled BSDF.
- Empty `AddBlock_SubPanel` body — this is where the block thumbnail picker needs to go.
- Empty `description` and basic `author` fields in `bl_info` — fill these in properly.
- The dead `scene.my_tool` reference — remove.

**Missing entirely (must build new):**

- Block library loading via `bpy.data.libraries.load()`.
- Thumbnail picker via `bpy.utils.previews`.
- Grid snapping enforcement (`tool_settings.use_snap`, snap increment = U).
- The "reveal mode" trainer-wheels system. This is the most important feature and the most novel part of SnapBlock — do not deprioritize it.
- Preset color swatches (the legacy code exposes Blender's native color picker, which works but is not the tap-a-swatch simplicity we want).
- `Block_<type>.<counter>` naming convention and the `SnapBlock Build` collection.
- Status-bar messages after each operator (`self.report({'INFO'}, "...")`).

**Bottom line:** roughly 30% of the scaffolding is reusable — the tedious-to-write but easy-to-extend parts. Use the legacy file as your starting skeleton rather than writing the register/panel boilerplate from scratch, then build the missing pieces on top.
