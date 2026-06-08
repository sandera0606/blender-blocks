r"""Run dev actions against the live Blender session from a terminal.

Sends one request to the dev bridge socket and prints the reply. Same wire
protocol as the MCP server, no MCP involved. Needs Blender open with the bridge
started (N-panel > SnapBlock Dev > Start Bridge Server, port 9876).

Usage (from the repo root):
    py dev\cli.py reload [MODULE]      reload the add-on (default: snapblock)
    py dev\cli.py reset [--force]      empty scene (File > New, no cube)
    py dev\cli.py dump [PATH]          list a .blend's contents (default: source library)
    py dev\cli.py scene               objects / collections / materials
    py dev\cli.py clear [COLLECTION]   clear a preview collection (default: SnapBlock Preview)
    py dev\cli.py py "CODE"            run bpy code

Stdlib only, so any Python runs it; no .venv or mcp package needed.
"""

import json
import socket
import sys
from pathlib import Path

HOST = "127.0.0.1"
PORT = 9876
REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_BLEND = REPO_ROOT / "source_blocks" / "all_blocks.blend"


def _call(tool, args):
    """Send the request JSON, half-close the write side so the bridge reads to EOF,
    then read the reply back. Same as mcp_server._call."""
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
                "Couldn't reach the Blender bridge on {}:{}. Is Blender open with the "
                "bridge started? (N-panel > SnapBlock Dev > Start Bridge Server)"
            ).format(HOST, PORT),
        }


def _render(resp):
    """Format a reply dict for printing. Same as mcp_server._render."""
    if not resp.get("ok"):
        return "BRIDGE ERROR:\n{}".format(resp.get("error", "unknown error"))
    parts = []
    if resp.get("stdout"):
        parts.append(resp["stdout"].rstrip())
    if resp.get("result") is not None:
        parts.append(resp["result"] if isinstance(resp["result"], str)
                     else json.dumps(resp["result"], indent=2))
    if resp.get("error"):
        parts.append("--- error (code raised) ---\n{}".format(resp["error"].rstrip()))
    return "\n\n".join(parts) if parts else "(no output)"


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "reload":
        tool, args = "reload_addon", {"module": rest[0] if rest else "snapblock"}
    elif cmd == "reset":
        tool, args = "reset_scene", {"force": "--force" in rest}
    elif cmd == "dump":
        path = next((a for a in rest if not a.startswith("-")), None)
        tool, args = "dump_library_state", {"blend_path": path or str(SOURCE_BLEND)}
    elif cmd == "scene":
        tool, args = "get_scene_summary", {}
    elif cmd == "clear":
        tool, args = "clear_preview", {"collection": rest[0] if rest else "SnapBlock Preview"}
    elif cmd == "py":
        if not rest:
            print('Usage: py dev\\cli.py py "CODE"')
            return 2
        tool, args = "run_python", {"code": rest[0]}
    else:
        print("Unknown command: {}\n".format(cmd))
        print(__doc__)
        return 2
    print(_render(_call(tool, args)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
