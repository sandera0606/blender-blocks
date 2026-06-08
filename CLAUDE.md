# CLAUDE.md

Guidance for Claude Code when working in this repository. Read `SNAPBLOCK_BRIEF.md` for the full design — it is the source of truth on scope, architecture, and rationale.

## What this is

SnapBlock is a **Blender 4.2+ add-on** that gives beginners a snap-block toy on top of a real Blender scene. The goal is to teach Blender through play, not to build a walled garden inside it.

## Repo state

- `SNAPBLOCK_BRIEF.md` — full design brief (source of truth).
- `snapblock/` — the add-on package (`constants.py`, `library.py`, `operators.py`, `panels.py`, `reveal.py`, `snapblock_library.blend`).
- `source_blocks/all_blocks.blend` — the user's master library, ~22 blocks in a collection named `"blocks"` (read-only).
- `tools/` — dev-time build/audit utilities. `dev/` — the MCP bridge (see Hard rule 5); not shipped.

## Hard rules

1. **Never modify `source_blocks/all_blocks.blend`.** It is read-only. The cleanup utility reads from it and writes to `snapblock/snapblock_library.blend`. Never include `bpy.ops.wm.save_as_mainfile()` in any script that touches the source path.
2. **Never auto-fix discrepancies in the user's blocks.** Inconsistent origins, unapplied scales, non-grid dimensions → report and wait for input. The user wants visibility, not silent fixes.
3. **Stay inside v0.1 scope.** The brief's "Out of scope for v0.1" list is binding. Confirm with the user before doing anything outside it.
4. **Never call the blocks "LEGO" or "bricks."** "Blocks" or "snap blocks." Legal/trademark, not stylistic.
5. **Run `bpy` via the dev bridge when it's up.** The `snapblock-blender` MCP tools (`run_python`, `get_scene_summary`, `dump_library_state`, `reload_addon`, …) execute in the live Blender session. If the bridge isn't running, fall back to copy-paste scripts that print clear, copy-pastable output. Setup and tool list: `dev/README.md`.

## Design rules (from the brief)

- **Glass-box.** Every operator leaves behind a normal Blender object/material/collection. No hidden state. If SnapBlock is uninstalled, the user's scene still works.
- **Reveal mode is core, not polish.** The "Show me what's really happening" toggle is the single most important differentiator and ships in v0.1.
- **Grid is 2mm.** `U = 0.002`, `H = 0.002`, defined in `snapblock/constants.py`. Store placements as integer grid coords `(gx, gy, gz)`; convert to world coords only at placement time. Enforce `bpy.context.scene.tool_settings.use_snap = True` with increment `U`.
- **Block loading.** `bpy.data.libraries.load()` to **append** (not link), so each placed block is editable.
- **Names and grouping.** Placed objects are `Block_<type>.<counter>` (e.g. `Block_2x4.001`) inside a collection called `SnapBlock Build`. The Outliner is part of the UX.
- **Materials.** Principled BSDF only. One material per color, named `SnapBlock_<colorname>`. No custom shader nodes, no transparency.
- **One operator per user action.** No mega-operators with branching behavior.
- **No magic numbers outside `constants.py`.**
- **User-facing strings.** Plain English, friendly, never condescending, no Python jargon. Errors via `self.report({'ERROR'}, ...)` — never let a traceback reach the user.

## Calibrating explanations

The user is **strong at Python, new to bpy**. So:

- Skip explanations of general Python (comprehensions, decorators, context managers, etc.).
- Explain bpy idioms when introducing them — why this pattern, what the alternatives are. The user wants to learn bpy through this project.
- Flag bpy gotchas inline (one-line comment or sentence). Operators behaving differently in script vs. UI contexts, dependency graph evaluation, data-block ownership, etc.
- If the user calls code ugly, trust them. Bad Python is bad Python; "that's how bpy code looks" is not a defense.

## Workflow

- Before writing a new module, state what it will contain and get buy-in.
- Before non-trivial changes to existing code, summarize the planned change first.
- To verify something about a `.blend` file, inspect it live (`dump_library_state`, `run_python`) rather than guessing; only write a paste-in script if the bridge is down.
- After editing the add-on, `reload_addon` and exercise the operator via `run_python` — no zip rebuild for dev iteration. Give zip/install steps only when the user is doing a real install.

## Build order

Defer to `SNAPBLOCK_BRIEF.md` → "First steps when you (Claude Code) start." Do not maintain a parallel build order here.

## Acceptance benchmark for v0.1

A new user can build a tiny house in ~90 seconds: place blocks, color them, see real Outliner objects.
