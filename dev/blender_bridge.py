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


def tool_get_viewport_screenshot(args):
    """Render the active 3D viewport to a PNG and return it base64-encoded.

    Captures what you'd see in the viewport (current angle + shading), without UI
    chrome, via an OpenGL render.
    """
    max_size = int(args.get("max_size", 1024))
    wm = bpy.context.window_manager
    win = bpy.context.window or (wm.windows[0] if wm.windows else None)
    if win is None:
        return {"ok": False, "error": "No Blender window available to capture."}
    area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return {"ok": False, "error": "No 3D viewport open. Switch an editor to the 3D Viewport and retry."}
    region = next((rg for rg in area.regions if rg.type == 'WINDOW'), None)

    path = os.path.join(tempfile.gettempdir(), "snapblock_viewport.png")
    render = bpy.context.scene.render
    # Stash and restore render settings so capturing doesn't mutate the user's scene.
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


TOOLS = {
    "run_python": tool_run_python,
    "get_scene_summary": tool_get_scene_summary,
    "dump_library_state": tool_dump_library_state,
    "get_viewport_screenshot": tool_get_viewport_screenshot,
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
        bpy.app.timers.register(_drain_queue)


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


_classes = (
    SNAPBLOCK_OT_start_bridge,
    SNAPBLOCK_OT_stop_bridge,
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
