# CLAUDE.md

Guidance for Claude Code when working in this repository. Read `SNAPBLOCK_BRIEF.md` for the full design — it is the source of truth on scope, architecture, and rationale.

## What this is

SnapBlock is a **Blender 4.2+ add-on** — a personal snap-block toy on top of a real Blender scene. Sandra likes building with snap-together blocks in Blender; this makes that less tedious and more fun. It's built for her own use, not for an audience. Every action leaves behind normal Blender data so the build stays editable by hand.

## Repo state

- `SNAPBLOCK_BRIEF.md` — full design brief (source of truth).
- `snapblock/` — the add-on package (`constants.py`, `library.py`, `operators.py`, `panels.py`, `snapblock_library.blend`).
- `source_blocks/all_blocks.blend` — the master library, ~22 blocks in a collection named `"blocks"` (read-only).
- `tools/` — dev-time build/audit utilities. `dev/` — the MCP bridge (see Hard rule 5); not shipped.

## Hard rules

1. **Never modify `source_blocks/all_blocks.blend`.** It is read-only. The cleanup utility reads from it and writes to `snapblock/snapblock_library.blend`. Never include `bpy.ops.wm.save_as_mainfile()` in any script that touches the source path.
2. **Never auto-fix discrepancies in the blocks.** Inconsistent origins, unapplied scales, non-grid dimensions → report and wait for input. Sandra wants visibility, not silent fixes.
3. **Confirm before scope creep.** The brief's "Not chasing these" list is the current focus boundary. Check before building something outside it.
4. **Call them "blocks" or "snap blocks," not "LEGO" or "bricks."** Just a naming choice for consistency — the shapes are custom anyway.
5. **Run `bpy` via the dev bridge when it's up.** The `snapblock-blender` MCP tools (`run_python`, `get_scene_summary`, `dump_library_state`, `reload_addon`, …) execute in the live Blender session. If the bridge isn't running, fall back to copy-paste scripts that print clear, copy-pastable output. Setup and tool list: `dev/README.md`.

## Design rules (from the brief)

- **Glass-box.** Every operator leaves behind a normal Blender object/material/collection. No hidden state. If SnapBlock is uninstalled, the scene still works — and Sandra can keep editing a build by hand in Blender at any time.
- **Grid is 1.0 BU.** `U = 1.0`, `H = 1.0`, defined in `snapblock/constants.py`. Store placements as integer grid coords `(gx, gy, gz)`; convert to world coords only at placement time. One cell lines up with Blender's default grid and increment-snap (which step by 1.0).
- **Block loading.** `bpy.data.libraries.load()` to **append** (not link), so each placed block is editable.
- **Names and grouping.** Placed objects are `Block_<type>.<counter>` (e.g. `Block_2x4.001`) inside a collection called `SnapBlock Build`. The Outliner is part of the UX.
- **Materials.** Principled BSDF only. One material per color, named `SnapBlock_<colorname>`. No custom shader nodes, no transparency.
- **One operator per user action.** No mega-operators with branching behavior.
- **No magic numbers outside `constants.py`.**
- **User-facing strings.** Plain English, friendly, never condescending, no Python jargon. Errors via `self.report({'ERROR'}, ...)` — never let a traceback reach the user.

## Calibrating explanations

Sandra is **strong at Python, new to bpy** — and wants to keep learning bpy by building this. So:

- Skip explanations of general Python (comprehensions, decorators, context managers, etc.).
- Explain bpy idioms when introducing them — why this pattern, what the alternatives are. This is the one place a teaching note belongs: it's for her, the builder, not an audience.
- Flag bpy gotchas inline (one-line comment or sentence). Operators behaving differently in script vs. UI contexts, dependency graph evaluation, data-block ownership, etc.
- If she calls code ugly, trust her. Bad Python is bad Python; "that's how bpy code looks" is not a defense.

## Workflow

- Before writing a new module, state what it will contain and get buy-in.
- Before non-trivial changes to existing code, summarize the planned change first.
- To verify something about a `.blend` file, inspect it live (`dump_library_state`, `run_python`) rather than guessing; only write a paste-in script if the bridge is down.
- After editing the add-on, `reload_addon` and exercise the operator via `run_python` — no zip rebuild for dev iteration. Give zip/install steps only when doing a real install.

## Build order

Defer to `SNAPBLOCK_BRIEF.md` → "Build order." Do not maintain a parallel build order here.

## When it's working

There's no benchmark and no audience to satisfy. It's working when building with it feels good — quick to place, snap, move, and color blocks, and the result is a real Blender scene worth keeping. The measure is whether it's fun to build with.
