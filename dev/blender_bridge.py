bl_info = {
    "name": "SnapBlock Dev Bridge",
    "author": "SnapBlock",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N-panel > SnapBlock Dev",
    "description": "Dev-only bridge: lets an external MCP server run bpy in this session.",
    "category": "Development",
}

# This add-on runs INSIDE Blender. It opens a localhost socket on a background
# thread so an external process (the MCP server) can ask Blender to run code.
#
# THE ONE HARD CONSTRAINT: bpy is NOT thread-safe. We must never call bpy from
# the socket thread. So the socket thread only parks each request on a Queue;
# a bpy.app.timers callback (which Blender runs on the MAIN thread) drains the
# queue, executes the tool, and signals the socket thread with a threading.Event.
# That hop from socket-thread -> main-thread is the whole reason this file looks
# more complicated than "just call exec()".

import bpy
import socket
import json
import queue
import threading
import traceback
import io
import os
import sys
import importlib
import base64
import tempfile
from contextlib import redirect_stdout

HOST = "127.0.0.1"
PORT = 9876
ACCEPT_TIMEOUT = 1.0   # so the accept loop wakes up to check the running flag
REQUEST_TIMEOUT = 60.0  # max wait for the main thread to produce a result
DRAIN_INTERVAL = 0.05   # how often the main-thread timer drains the queue

# Module-level server state. A dict (not globals) so the operators can mutate it.
_state = {"sock": None, "thread": None, "running": False}
_queue = queue.Queue()


# --- Tools (these run on the MAIN thread, so bpy is safe here) ----------------

def tool_run_python(args):
    """Execute arbitrary code with bpy in scope. stdout and tracebacks come back
    as data, never as a crash. Convention: set a variable named `result` and its
    repr is returned too."""
    code = args.get("code", "")
    namespace = {"bpy": bpy, "__name__": "__snapblock_exec__"}
    buf = io.StringIO()
    error = None
    try:
        with redirect_stdout(buf):
            exec(code, namespace)
    except Exception:
        error = traceback.format_exc()
    result = repr(namespace["result"]) if "result" in namespace else None
    return {"ok": True, "stdout": buf.getvalue(), "result": result, "error": error}


def tool_get_scene_summary(args):
    """Structured snapshot of the current scene: objects, collections, materials."""
    scene = bpy.context.scene
    objects = [
        {
            "name": o.name,
            "type": o.type,
            "location": [round(c, 4) for c in o.location],
            "collections": [c.name for c in o.users_collection],
        }
        for o in scene.objects
    ]
    return {
        "ok": True,
        "result": {
            "objects": objects,
            "collections": [c.name for c in bpy.data.collections],
            "materials": [m.name for m in bpy.data.materials],
        },
    }


def tool_dump_library_state(args):
    """List what a .blend contains WITHOUT appending anything.

    bpy gotcha: `libraries.load(path)` opens the file read-only. Just reading the
    `data_from` side lists datablock NAMES; nothing is appended until you assign
    into `data_to`. We assign nothing -> the source file and the current session
    are both untouched. (This is the safe way to honour 'never modify the source'.)
    """
    path = args.get("blend_path")
    if not path or not os.path.exists(path):
        return {"ok": False, "error": "blend not found: {}".format(path)}
    info = {}
    with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
        info["objects"] = list(data_from.objects)
        info["collections"] = list(data_from.collections)
        info["meshes"] = list(data_from.meshes)
        info["materials"] = list(data_from.materials)
    return {"ok": True, "result": info}


def _capture_viewport_png(win, area, region, max_size):
    """Render the given VIEW_3D area to a PNG and return {ok, image_png_b64}.

    Stashes/restores the scene's render settings so capturing leaves the user's
    scene untouched. Shared by the plain and framed screenshot paths.
    """
    path = os.path.join(tempfile.gettempdir(), "snapblock_viewport.png")
    render = bpy.context.scene.render
    saved = (render.filepath, render.image_settings.file_format,
             render.resolution_x, render.resolution_y, render.resolution_percentage)
    try:
        w, h = area.width, area.height
        scale = min(1.0, max_size / float(max(w, h)))  # cap the longest side, keep aspect
        render.image_settings.file_format = 'PNG'
        render.filepath = path
        render.resolution_x = max(1, int(w * scale))
        render.resolution_y = max(1, int(h * scale))
        render.resolution_percentage = 100
        # bpy gotcha: render.opengl needs a VIEW_3D area in context, and the timer
        # callback's default context doesn't have one. Override it explicitly.
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.render.opengl(write_still=True, view_context=True)
    except Exception:
        return {"ok": False, "error": traceback.format_exc()}
    finally:
        (render.filepath, render.image_settings.file_format,
         render.resolution_x, render.resolution_y, render.resolution_percentage) = saved

    with open(path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode("ascii")
    return {"ok": True, "image_png_b64": encoded}


def _frame_view(win, area, region, target):
    """Point the given viewport at the interesting objects before a screenshot:
    the `target` collection if named and non-empty, else `SnapBlock Preview` if it
    exists, otherwise everything. Best-effort — never fails the screenshot — and
    stashes/restores the selection so framing stays glass-box-clean.
    """
    name = target or "SnapBlock Preview"
    coll = bpy.data.collections.get(name)
    view = bpy.context.view_layer
    saved_active = view.objects.active
    saved_selected = list(bpy.context.selected_objects)
    try:
        with bpy.context.temp_override(window=win, area=area, region=region):
            if coll is not None and len(coll.objects) > 0:
                bpy.ops.object.select_all(action='DESELECT')
                for o in coll.objects:
                    o.select_set(True)
                view.objects.active = coll.objects[0]
                bpy.ops.view3d.view_selected()
            else:
                bpy.ops.view3d.view_all()
    except Exception:
        return  # framing is best-effort; a screenshot of the current view still beats none
    finally:
        # Restore whatever was selected before we hijacked the selection to frame.
        try:
            for o in bpy.context.selected_objects:
                o.select_set(False)
            for o in saved_selected:
                o.select_set(True)
            view.objects.active = saved_active
        except Exception:
            pass


def tool_get_viewport_screenshot(args):
    """Render the active 3D viewport to a PNG and return it base64-encoded.

    Captures what you'd see in the viewport (current angle + shading), without UI
    chrome, via an OpenGL render. With frame=True, first points the view at the
    target/`SnapBlock Preview` collection (else frames all) so the capture is
    centered on the thing being checked.
    """
    max_size = int(args.get("max_size", 1024))
    frame = bool(args.get("frame", False))
    target = args.get("target", "")
    wm = bpy.context.window_manager
    win = bpy.context.window or (wm.windows[0] if wm.windows else None)
    if win is None:
        return {"ok": False, "error": "No Blender window available to capture."}
    area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return {"ok": False, "error": "No 3D viewport open. Switch an editor to the 3D Viewport and retry."}
    region = next((rg for rg in area.regions if rg.type == 'WINDOW'), None)

    if frame:
        _frame_view(win, area, region, target)
    return _capture_viewport_png(win, area, region, max_size)


def tool_reload_addon(args):
    """Reload a SnapBlock package from the working tree so file edits take effect
    without rebuilding/reinstalling a zip.

    bpy note: classes double-register if register() runs without a prior
    unregister(), so we unregister the loaded version first, then evict the package
    and all its submodules from sys.modules so the re-import is genuinely fresh
    (importlib.reload alone won't re-pull edited submodules in dependency order). A
    register() that fails partway may leave some classes registered; the returned
    traceback is the signal to fix the file and call this again.
    """
    module = args.get("module", "snapblock")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)  # so `import snapblock` resolves from the repo, no zip install

    notes = []
    old = sys.modules.get(module)
    if old is not None and hasattr(old, "unregister"):
        try:
            old.unregister()
        except Exception:
            notes.append("prior unregister() raised (continuing):\n" + traceback.format_exc())

    for name in [m for m in list(sys.modules) if m == module or m.startswith(module + ".")]:
        del sys.modules[name]

    error = None
    try:
        mod = importlib.import_module(module)
        mod.register()
    except Exception:
        error = traceback.format_exc()

    stdout = "\n".join(notes) if notes else "reloaded {}".format(module)
    return {"ok": True, "stdout": stdout, "error": error}


def tool_clear_preview(args):
    """Remove a preview collection and the datablocks it owns, leaving the rest of
    the scene intact.

    A mesh/material is only deleted if removing the preview objects drops it to 0
    users, so anything the user also uses elsewhere keeps a user and survives. This
    is what makes a preview cleanly reversible.
    """
    name = args.get("collection", "SnapBlock Preview")
    coll = bpy.data.collections.get(name)
    if coll is None:
        return {"ok": True, "stdout": "nothing to clear (no '{}' collection)".format(name)}

    objs = list(coll.objects)
    meshes = {o.data for o in objs if o.type == 'MESH' and o.data is not None}
    mats = {m for o in objs if o.type == 'MESH'
            for m in o.data.materials if m is not None}

    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)

    n_mesh = 0
    for me in meshes:
        if me.users == 0:
            bpy.data.meshes.remove(me)
            n_mesh += 1
    n_mat = 0
    for ma in mats:
        if ma.users == 0:
            bpy.data.materials.remove(ma)
            n_mat += 1
    bpy.data.collections.remove(coll)

    return {"ok": True, "stdout": "Cleared '{}': {} objects, {} meshes, {} materials.".format(
        name, len(objs), n_mesh, n_mat)}


def tool_reset_scene(args):
    """Load an empty file (like File > New, but with no default cube) to get a clean
    datablock namespace for the append/build tools.

    Destructive: refuses when there are unsaved changes unless force=True. Relies on
    the queue-drain timer being registered persistent=True, or it would be dropped by
    this file load and the bridge would stop responding.
    """
    if bpy.data.is_dirty and not args.get("force"):
        return {"ok": False, "error": "Unsaved changes — save first, or call with force=true."}
    bpy.ops.wm.read_homefile(use_empty=True)
    return {"ok": True, "stdout": "Scene reset to an empty file."}


TOOLS = {
    "run_python": tool_run_python,
    "get_scene_summary": tool_get_scene_summary,
    "dump_library_state": tool_dump_library_state,
    "get_viewport_screenshot": tool_get_viewport_screenshot,
    "reload_addon": tool_reload_addon,
    "clear_preview": tool_clear_preview,
    "reset_scene": tool_reset_scene,
}


# --- Main-thread queue drain (registered as a Blender timer) ------------------

def _drain_queue():
    """Runs on the MAIN thread. Executes every queued request and signals its
    waiting socket-thread. Returning a float reschedules the timer."""
    while not _queue.empty():
        job = _queue.get_nowait()
        try:
            resp = TOOLS[job["tool"]](job["args"])
        except KeyError:
            resp = {"ok": False, "error": "unknown tool: {}".format(job["tool"])}
        except Exception:
            resp = {"ok": False, "error": traceback.format_exc()}
        job["response"].update(resp)
        job["event"].set()
    return DRAIN_INTERVAL


# --- Socket server (background thread; NO bpy calls in here) ------------------

def _recv_all(conn):
    chunks = []
    while True:
        data = conn.recv(4096)
        if not data:  # client half-closed its write side -> full request received
            break
        chunks.append(data)
    return b"".join(chunks)


def _serve():
    while _state["running"]:
        try:
            conn, _ = _state["sock"].accept()
        except socket.timeout:
            continue
        except OSError:
            break  # socket was closed by stop()
        with conn:
            try:
                req = json.loads(_recv_all(conn).decode("utf-8"))
                event = threading.Event()
                holder = {}
                _queue.put({
                    "tool": req["tool"],
                    "args": req.get("args", {}),
                    "event": event,
                    "response": holder,
                })
                if event.wait(timeout=REQUEST_TIMEOUT):
                    resp = holder
                else:
                    resp = {"ok": False, "error": "timed out waiting for Blender main thread"}
            except Exception:
                resp = {"ok": False, "error": traceback.format_exc()}
            try:
                conn.sendall(json.dumps(resp).encode("utf-8"))
            except OSError:
                pass


def _start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.settimeout(ACCEPT_TIMEOUT)
    sock.listen(1)
    _state["sock"] = sock
    _state["running"] = True
    _state["thread"] = threading.Thread(target=_serve, daemon=True)
    _state["thread"].start()
    if not bpy.app.timers.is_registered(_drain_queue):
        # persistent=True so the timer survives file loads (read_homefile / File > Open).
        # A non-persistent timer is silently dropped on load -> the queue stops draining
        # -> every later request times out. reset_scene depends on this.
        bpy.app.timers.register(_drain_queue, persistent=True)


def _stop_server():
    _state["running"] = False
    if _state["sock"] is not None:
        _state["sock"].close()
        _state["sock"] = None
    if bpy.app.timers.is_registered(_drain_queue):
        bpy.app.timers.unregister(_drain_queue)


# --- Operators + panel --------------------------------------------------------

class SNAPBLOCK_OT_start_bridge(bpy.types.Operator):
    bl_idname = "snapblock.start_bridge"
    bl_label = "Start Bridge Server"
    bl_description = "Open the localhost socket so the MCP server can drive this session"

    def execute(self, context):
        if _state["running"]:
            self.report({'INFO'}, "Bridge already running.")
            return {'CANCELLED'}
        try:
            _start_server()
        except OSError as exc:
            self.report({'ERROR'}, "Couldn't start bridge: {}".format(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, "Bridge listening on {}:{}".format(HOST, PORT))
        return {'FINISHED'}


class SNAPBLOCK_OT_stop_bridge(bpy.types.Operator):
    bl_idname = "snapblock.stop_bridge"
    bl_label = "Stop Bridge Server"
    bl_description = "Close the bridge socket"

    def execute(self, context):
        _stop_server()
        self.report({'INFO'}, "Bridge stopped.")
        return {'FINISHED'}


# --- Dev-action operators (panel buttons) -------------------------------------
# Buttons that call the same tool_* functions as the socket path, so a click and a
# CLI/MCP call run the same code. Operators run on the main thread, so bpy is safe.

def _report_reply(op, reply):
    """Report a tool_* reply through the operator's report system."""
    if not reply.get("ok"):
        op.report({'ERROR'}, reply.get("error", "failed"))
        return {'CANCELLED'}
    if reply.get("error"):  # ok=True but the run raised (e.g. a failed register())
        op.report({'ERROR'}, reply["error"].strip().splitlines()[-1])
        return {'CANCELLED'}
    msg = (reply.get("stdout") or "Done.").strip().splitlines()[-1]
    op.report({'INFO'}, msg)
    return {'FINISHED'}


class SNAPBLOCK_OT_dev_reload(bpy.types.Operator):
    bl_idname = "snapblock.dev_reload"
    bl_label = "Reload snapblock"
    bl_description = "Reload the snapblock add-on from the working tree (apply file edits)"

    def execute(self, context):
        return _report_reply(self, tool_reload_addon({}))


class SNAPBLOCK_OT_dev_reset(bpy.types.Operator):
    bl_idname = "snapblock.dev_reset"
    bl_label = "Reset Scene"
    bl_description = "Empty scene (File > New, no cube). Refuses if there are unsaved changes"

    def execute(self, context):
        return _report_reply(self, tool_reset_scene({}))


class SNAPBLOCK_OT_dev_clear(bpy.types.Operator):
    bl_idname = "snapblock.dev_clear"
    bl_label = "Clear Preview"
    bl_description = "Remove the SnapBlock Preview collection and the data it brought in"

    def execute(self, context):
        return _report_reply(self, tool_clear_preview({}))


class SNAPBLOCK_OT_dev_dump(bpy.types.Operator):
    bl_idname = "snapblock.dev_dump"
    bl_label = "Dump Library"
    bl_description = "Print the source block library's contents to the system console"

    def execute(self, context):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(repo_root, "source_blocks", "all_blocks.blend")
        reply = tool_dump_library_state({"blend_path": path})
        if not reply.get("ok"):
            self.report({'ERROR'}, reply.get("error", "failed"))
            return {'CANCELLED'}
        info = reply["result"]
        print("--- source library ---")
        print(json.dumps(info, indent=2))
        self.report({'INFO'}, "Listed {} objects (see system console).".format(
            len(info.get("objects", []))))
        return {'FINISHED'}


class SNAPBLOCK_OT_dev_scene(bpy.types.Operator):
    bl_idname = "snapblock.dev_scene"
    bl_label = "Scene Summary"
    bl_description = "Print the scene's objects/collections/materials to the system console"

    def execute(self, context):
        info = tool_get_scene_summary({})["result"]
        print("--- scene summary ---")
        print(json.dumps(info, indent=2))
        self.report({'INFO'}, "{} objects, {} collections, {} materials (see console).".format(
            len(info["objects"]), len(info["collections"]), len(info["materials"])))
        return {'FINISHED'}


class SNAPBLOCK_PT_dev(bpy.types.Panel):
    bl_label = "SnapBlock Dev"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SnapBlock Dev"

    def draw(self, context):
        layout = self.layout
        if _state["running"]:
            layout.label(text="Listening on {}:{}".format(HOST, PORT), icon='RADIOBUT_ON')
            layout.operator("snapblock.stop_bridge", icon='PAUSE')
        else:
            layout.label(text="Stopped", icon='RADIOBUT_OFF')
            layout.operator("snapblock.start_bridge", icon='PLAY')

        # These run in-process, so they work even when the socket server is stopped.
        layout.separator()
        col = layout.column(align=True)
        col.label(text="Dev actions:")
        col.operator("snapblock.dev_reload", icon='FILE_REFRESH')
        col.operator("snapblock.dev_reset", icon='FILE_NEW')
        col.operator("snapblock.dev_dump", icon='ASSET_MANAGER')
        col.operator("snapblock.dev_scene", icon='SCENE_DATA')
        col.operator("snapblock.dev_clear", icon='TRASH')


_classes = (
    SNAPBLOCK_OT_start_bridge,
    SNAPBLOCK_OT_stop_bridge,
    SNAPBLOCK_OT_dev_reload,
    SNAPBLOCK_OT_dev_reset,
    SNAPBLOCK_OT_dev_clear,
    SNAPBLOCK_OT_dev_dump,
    SNAPBLOCK_OT_dev_scene,
    SNAPBLOCK_PT_dev,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    _stop_server()  # make sure the socket/timer don't outlive the add-on
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
