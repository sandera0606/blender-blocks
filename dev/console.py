r"""Dev-loop helpers for Blender's Python console.

Thin wrappers over the bridge's tool_* functions, called in-process. They work
whenever the SnapBlock Dev Bridge add-on is enabled; you don't need to Start
Bridge Server, since the console already runs on the main thread.

To load, paste these two lines into the console (point the first at your checkout).
The exec drops every function into the console namespace:

    SNAPBLOCK_REPO = r"C:\Users\shuan\Documents\personal\Coding\snapblock"
    exec(open(SNAPBLOCK_REPO + r"\dev\console.py").read())

Then call reload(), reset(), dump(), scene(), clear(), py("..."), or helpme().
"""

import os
import json

try:
    import blender_bridge as _bridge
except ImportError:
    raise RuntimeError(
        "Can't import the SnapBlock Dev Bridge add-on. Enable it in "
        "Edit > Preferences > Add-ons (search 'SnapBlock Dev Bridge'), then reload this."
    )

# SNAPBLOCK_REPO comes from the loader line (exec shares our namespace). Fall back
# to the cwd if it wasn't set.
try:
    _REPO = SNAPBLOCK_REPO  # noqa: F821 - provided by the loader
except NameError:
    _REPO = os.getcwd()

_SOURCE_BLEND = os.path.join(_REPO, "source_blocks", "all_blocks.blend")


def _show(reply):
    """Print a reply dict: stdout, result, then any traceback."""
    if not reply.get("ok"):
        print("ERROR:", reply.get("error", "unknown error"))
        return
    if reply.get("stdout"):
        print(reply["stdout"].rstrip())
    if reply.get("result") is not None:
        res = reply["result"]
        print(res if isinstance(res, str) else json.dumps(res, indent=2))
    if reply.get("error"):
        print("--- error (code raised) ---")
        print(reply["error"].rstrip())


def reload(module="snapblock"):
    """Reload the snapblock package from your working tree (apply file edits)."""
    _show(_bridge.tool_reload_addon({"module": module}))


def reset(force=False):
    """Empty scene (File > New, no cube). Refuses on unsaved changes unless force=True."""
    _show(_bridge.tool_reset_scene({"force": force}))


def dump(path=None):
    """List a .blend's contents without appending. Defaults to the source library."""
    _show(_bridge.tool_dump_library_state({"blend_path": path or _SOURCE_BLEND}))


def scene():
    """Print objects / collections / materials in the current scene."""
    _show(_bridge.tool_get_scene_summary({}))


def clear(collection="SnapBlock Preview"):
    """Remove a preview collection and the meshes/materials it brought in."""
    _show(_bridge.tool_clear_preview({"collection": collection}))


def py(code):
    """Run arbitrary bpy code; print stdout / result / traceback."""
    _show(_bridge.tool_run_python({"code": code}))


def helpme():
    """List the commands. Named helpme to avoid shadowing builtin help."""
    print(
        "SnapBlock dev console:\n"
        "  reload()            reload the snapblock add-on from the working tree\n"
        "  reset(force=False)  empty scene for clean appends\n"
        "  dump(path=None)     list a .blend's contents (default: source library)\n"
        "  scene()             objects / collections / materials\n"
        "  clear()             remove the SnapBlock Preview collection\n"
        "  py('code')          run bpy code\n"
        "  helpme()            this list"
    )


print("SnapBlock dev console loaded. Type helpme() for commands.")
