r"""SnapBlock MCP server.

Runs in a NORMAL Python venv (not Blender's bundled Python). It exposes a few
tools to Claude Code over stdio; each tool opens a localhost socket to the
Blender-side bridge (dev/blender_bridge.py), sends one JSON request, and returns
the reply. The Blender add-on must be running with its bridge server started
(N-panel > SnapBlock Dev > Start Bridge Server).

Setup (run from the repo root):
    pip install mcp
    claude mcp add snapblock-blender -- .\.venv\Scripts\python.exe .\dev\mcp_server.py
"""

import base64
import json
import socket
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

HOST = "127.0.0.1"
PORT = 9876
REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_BLEND = REPO_ROOT / "source_blocks" / "all_blocks.blend"

mcp = FastMCP("snapblock-blender")


def _call(tool, args):
    """One request per connection. Send JSON, half-close write so the bridge
    reads to EOF, then read the reply to EOF."""
    try:
        with socket.create_connection((HOST, PORT), timeout=90) as s:
            s.sendall(json.dumps({"tool": tool, "args": args}).encode("utf-8"))
            s.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                data = s.recv(4096)
                if not data:
                    break
                chunks.append(data)
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (ConnectionRefusedError, OSError):
        return {
            "ok": False,
            "error": (
                "Couldn't reach the Blender bridge on {}:{}. Is Blender open with "
                "the bridge started? (N-panel > SnapBlock Dev > Start Bridge Server)"
            ).format(HOST, PORT),
        }


def _render(resp):
    """Turn the bridge's reply dict into readable text for the agent."""
    if not resp.get("ok"):
        return "BRIDGE ERROR:\n{}".format(resp.get("error", "unknown error"))
    parts = []
    if resp.get("stdout"):
        parts.append("--- stdout ---\n{}".format(resp["stdout"].rstrip()))
    if resp.get("result") is not None:
        parts.append("--- result ---\n{}".format(
            resp["result"] if isinstance(resp["result"], str)
            else json.dumps(resp["result"], indent=2)
        ))
    if resp.get("error"):
        parts.append("--- error (code raised) ---\n{}".format(resp["error"].rstrip()))
    return "\n\n".join(parts) if parts else "(no output)"


@mcp.tool()
def run_python(code: str) -> str:
    """Run Python with `bpy` in scope inside the live Blender session.

    stdout and any traceback are captured and returned (errors never crash
    Blender). Set a variable named `result` to have its repr returned too.
    """
    return _render(_call("run_python", {"code": code}))


@mcp.tool()
def get_scene_summary() -> str:
    """Snapshot of the current Blender scene: objects (name/type/location/
    collections), all collections, and all materials."""
    return _render(_call("get_scene_summary", {}))


@mcp.tool()
def dump_library_state(blend_path: str = "") -> str:
    """List the contents (objects, collections, meshes, materials) of a .blend
    WITHOUT appending anything. Defaults to the read-only source block library.
    """
    path = blend_path or str(SOURCE_BLEND)
    return _render(_call("dump_library_state", {"blend_path": path}))


@mcp.tool()
def get_viewport_screenshot(max_size: int = 1024, frame: bool = False, target: str = "") -> Image:
    """Capture the live Blender 3D viewport as an image.

    Use this SPARINGLY, only when the thing you need to confirm is genuinely
    visual (does the build look right, is a block floating or mis-colored, is the
    camera framing sensible). For checking names, coordinates, counts, materials,
    or whether an operator ran, prefer the cheaper text tools (get_scene_summary
    or a run_python assertion) instead of a screenshot.

    Set frame=True to point the view at the `target` collection (or the
    `SnapBlock Preview` collection, else everything) before capturing, so the shot
    is centered on what you're checking instead of the current camera angle.
    """
    resp = _call("get_viewport_screenshot", {"max_size": max_size, "frame": frame, "target": target})
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "screenshot failed"))
    return Image(data=base64.b64decode(resp["image_png_b64"]), format="png")


@mcp.tool()
def reload_addon(module: str = "snapblock") -> str:
    """Reload a SnapBlock package from the repo working tree in the live session.

    Use after editing files under `snapblock/` to apply the changes without
    rebuilding/reinstalling a zip: it unregisters the old version, re-imports the
    package fresh, and calls register(). A failed register() comes back as a
    traceback string (Blender doesn't crash) — fix the file and call again.
    """
    return _render(_call("reload_addon", {"module": module}))


@mcp.tool()
def clear_preview(collection: str = "SnapBlock Preview") -> str:
    """Remove a preview collection and the datablocks it brought in, reverting a
    preview you appended into the user's live scene.

    Only deletes meshes/materials that drop to 0 users once the preview objects are
    gone, so anything the user also uses elsewhere is left untouched.
    """
    return _render(_call("clear_preview", {"collection": collection}))


@mcp.tool()
def reset_scene(force: bool = False) -> str:
    """Load an empty file (File > New, no default cube) for a clean datablock
    namespace — chiefly before running the append/build tools, which otherwise
    suffix names (.001) when blocks of the same name already exist.

    DESTRUCTIVE: discards the current scene. Refuses if there are unsaved changes
    unless force=True. Not for inspection — use a preview + clear_preview for that.
    """
    return _render(_call("reset_scene", {"force": force}))


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
