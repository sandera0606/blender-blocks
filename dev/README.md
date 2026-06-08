# SnapBlock Dev Bridge (MCP)

Dev-only tooling that lets Claude Code run `bpy` directly inside your live
Blender session — no more copy-paste loop. **Not part of the SnapBlock add-on.**
Keep it out of any shipped zip.

## About SnapBlock

SnapBlock is a **Blender 4.2+ add-on** that puts a snap-block toy on top of a
real Blender scene — the goal is to teach Blender through play, not to build a
walled garden inside it. Beginners place blocks on a 2mm grid, color them, and
end up with normal Blender objects, materials, and collections they can keep
working with. Its defining feature is **Reveal mode** ("show me what's really
happening"), which surfaces the actual Blender data behind the toy.

See `SNAPBLOCK_BRIEF.md` (repo root) for the full design and `CLAUDE.md` for the
working rules — notably: the block library in `source_blocks/all_blocks.blend`
is **read-only**, and the blocks are never called "LEGO" or "bricks."

### Why this bridge exists

`bpy` only exists inside Blender, so Claude Code normally can't run it — every
diagnostic means writing a script for a human to paste into Blender's Scripting
tab and paste the output back. This bridge closes that loop: Claude calls a tool,
the code runs in the live session, and the result comes straight back. That makes
inspecting `.blend` state, checking the scene, and verifying changes much faster.

## Architecture

```
Claude Code ──stdio──► mcp_server.py ──TCP :9876──► blender_bridge.py
(MCP client)           (your venv)                  (inside Blender)
```

Two runtimes: the MCP server runs in a normal Python venv; the bridge runs
inside Blender. They talk over a localhost socket.

`bpy` is not thread-safe, so the bridge never calls it from the socket thread.
Each request is parked on a `queue.Queue` and executed on Blender's **main
thread** by a `bpy.app.timers` callback, which signals the socket thread back
with a `threading.Event`. That main-thread hop is the whole reason the bridge is
more than a one-liner.

## Tools exposed

| Tool                      | What it does                                                    |
|---------------------------|----------------------------------------------------------------|
| `run_python`              | Run arbitrary code with `bpy` in scope; stdout + tracebacks return as data. Set `result = ...` to also get its repr. |
| `get_scene_summary`       | Objects (name/type/location/collections), collections, materials. |
| `dump_library_state`      | List a `.blend`'s contents without appending. Defaults to the read-only `source_blocks/all_blocks.blend`. |
| `get_viewport_screenshot` | Render the live 3D viewport to an image. Used only when a check is genuinely visual. `frame=True` points the view at the `SnapBlock Preview`/`target` collection (else frames all) first. |
| `reload_addon`            | Re-import the `snapblock` package from the repo tree and re-run `register()`, so file edits apply with no zip rebuild/reinstall. Failed registration returns as a traceback, not a crash. |
| `clear_preview`           | Remove a `SnapBlock Preview` collection and the meshes/materials it brought in (only those that drop to 0 users), reverting a preview cleanly. |
| `reset_scene`             | Load an empty file (File > New, no default cube) for a clean namespace before the append/build tools. Destructive; refuses on unsaved changes unless `force=True`. |

## The dev loop (editing the add-on)

Once the `snapblock/` package exists, iterate without rebuilding a zip:

1. Edit a file under `snapblock/` on disk.
2. Call `reload_addon` — it re-imports the package and re-runs `register()` in the
   live session. A syntax/registration error comes back as a traceback string.
3. Exercise the changed operator via `run_python` (same code path as the button).

`reload_addon` adds the repo root to `sys.path`, so the package loads straight from
the working tree — no Install-from-Disk step.

## Showing the user something (preview → verify → revert)

When a check genuinely needs the user's eyes (does the cleaned library look right?),
don't hand over a screenshot — put it in *their* scene and let them look:

1. Append/lay the objects into a collection named **`SnapBlock Preview`** via
   `run_python`, linked only to that collection (not the scene's master collection).
2. The user inspects directly — orbit, Outliner, click — in their own Blender.
3. Call `clear_preview` to remove exactly what was added. It only deletes meshes/
   materials that drop to 0 users, so the user's pre-existing data survives. (The
   file's "modified" flag will be set, but nothing is saved — content is restored.)

## How changes get verified

- **Exercising the add-on:** clicking a panel button just calls an operator, so
  Claude tests features by calling the same operator through `run_python` (e.g.
  `bpy.ops.snapblock.add_block()`). Same code path as the button. Modal /
  drag-style operators can't be driven from script and need manual testing.
- **Checking results:** cheap text first (`get_scene_summary`, or a `run_python`
  assertion on names/coords/colors). `get_viewport_screenshot` (optionally
  `frame=True`) is for Claude's own visual self-check — is a block floating,
  mis-colored, mis-sized — not for routine confirmation. Things that genuinely need
  *human* sign-off use the preview→verify→revert loop above.

## One-time setup

1. **Install the MCP SDK** in a venv (run from the repo root):
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\pip install mcp
   ```
2. **Register the server with Claude Code** :
   ```powershell
   claude mcp add snapblock-blender -- .\.venv\Scripts\python.exe .\dev\mcp_server.py
   ```
3. **Install the bridge add-on in Blender:**
   - Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk… ▸ pick `dev\blender_bridge.py`.
   - Enable "SnapBlock Dev Bridge".

## Each session

1. In Blender: press `N` in the 3D viewport ▸ **SnapBlock Dev** tab ▸
   **Start Bridge Server**. It should read `Listening on 127.0.0.1:9876`.
2. Start (or restart) Claude Code in this repo so it picks up the
   `snapblock-blender` MCP server. Its tools are then live.

## Running it yourself (no Claude)

The MCP tools are just a remote front-end for the `tool_*` functions in
`blender_bridge.py`. You can hit those same functions three other ways, so the
common dev actions (reload the add-on, reset the scene, dump the library, scene
summary, clear a preview) don't need to go through Claude.

All three run the same code; pick whichever is in reach.

### 1. Blender's Python console

In-process, so it only needs the bridge add-on *enabled* — you do **not** have to
Start Bridge Server. Open the console (Scripting workspace, or switch an editor to
Python Console) and paste these two lines once per session. Point the first at your
checkout:

```python
SNAPBLOCK_REPO = r"C:\Users\shuan\Documents\personal\Coding\snapblock"
exec(open(SNAPBLOCK_REPO + r"\dev\console.py").read())
```

Then call any of:

```python
reload()            # reload the snapblock add-on from the working tree
reset(force=False)  # empty scene (File > New, no cube); refuses if unsaved
dump(path=None)     # list a .blend's contents (default: the source library)
scene()             # objects / collections / materials
clear()             # remove the SnapBlock Preview collection
py("...")           # run arbitrary bpy code
helpme()            # this list
```

### 2. Terminal (PowerShell)

Talks to the bridge over the socket, so it **does** need Start Bridge Server
running. Stdlib only — any Python works, no `.venv` or `mcp` needed. From the repo
root:

```powershell
py dev\cli.py reload          # reload the add-on (optional MODULE arg)
py dev\cli.py reset --force   # empty scene
py dev\cli.py dump            # source library (or pass a PATH)
py dev\cli.py scene
py dev\cli.py clear           # optional COLLECTION arg
py dev\cli.py py "bpy.ops.snapblock.add_block()"
py dev\cli.py --help
```

### 3. N-panel buttons

`N` in the 3D viewport ▸ **SnapBlock Dev** tab ▸ the **Dev actions** group:
Reload / Reset / Dump / Scene / Clear. Dump and Scene print to the system console
(Window ▸ Toggle System Console). These run in-process too, so they work even with
the bridge server stopped.

**Heads up:** if you installed the bridge via *Install from Disk*, Blender runs a
*copy* under `…/scripts/addons/blender_bridge.py`, not the file in this repo. After
editing `blender_bridge.py` (e.g. to change these buttons), re-copy it over that
install path, then toggle the add-on off/on (or restart Blender) to pick it up. The
console and CLI helpers are unaffected — they don't depend on those edits.

## Smoke test

Ask Claude to call `run_python` with:
```python
print(bpy.app.version_string)
result = len(bpy.data.objects)
```
You should get the Blender version and an object count back.

## Notes / safety

- `run_python` is arbitrary code execution inside Blender. Fine for solo dev on
  your machine; never ship the bridge enabled in the actual add-on.
- The bridge binds to `127.0.0.1` only (not reachable off-machine).
- A request blocks until the main thread is free (e.g. it won't run mid-render).
  60s timeout per request.
- `dump_library_state` opens blends read-only and appends nothing, so it can
  inspect `source_blocks/all_blocks.blend` without violating the never-modify rule.
