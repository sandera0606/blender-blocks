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
| `get_viewport_screenshot` | Render the live 3D viewport to an image. Used only when a check is genuinely visual. |

## How changes get verified

- **Exercising the add-on:** clicking a panel button just calls an operator, so
  Claude tests features by calling the same operator through `run_python` (e.g.
  `bpy.ops.snapblock.add_block()`). Same code path as the button. Modal /
  drag-style operators can't be driven from script and need manual testing.
- **Checking results:** cheap text first (`get_scene_summary`, or a `run_python`
  assertion on names/coords/colors). `get_viewport_screenshot` is reserved for
  when the question is actually visual, not for routine confirmation.

## One-time setup

1. **Install the MCP SDK** in a venv:
   ```powershell
   cd C:\Users\shuan\Documents\personal\Coding\snapblock
   py -m venv .venv
   .\.venv\Scripts\pip install mcp
   ```
2. **Register the server with Claude Code** (use the venv's python, absolute paths):
   ```powershell
   claude mcp add snapblock-blender -- C:\Users\shuan\Documents\personal\Coding\snapblock\.venv\Scripts\python.exe C:\Users\shuan\Documents\personal\Coding\snapblock\dev\mcp_server.py
   ```
3. **Install the bridge add-on in Blender:**
   - Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk… ▸ pick `dev\blender_bridge.py`.
   - Enable "SnapBlock Dev Bridge".

## Each session

1. In Blender: press `N` in the 3D viewport ▸ **SnapBlock Dev** tab ▸
   **Start Bridge Server**. It should read `Listening on 127.0.0.1:9876`.
2. Start (or restart) Claude Code in this repo so it picks up the
   `snapblock-blender` MCP server. Its tools are then live.

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
