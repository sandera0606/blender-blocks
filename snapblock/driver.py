"""
The "follow a manual" driver — the in-Blender consumer of a build-plan JSON.

A build plan (see ../docs/build_plan.md) is the file the standalone manual generator
(manual/, pure Python) turns into a PDF. This module reads the SAME file to drive a
guided HAND-build inside Blender: it tracks which step you're on, derives the parts list,
records honor-system checkoff, and organises hand-placed blocks into one collection per
"bag". It deliberately does NOT place the build blocks for you — you read the step and
build it yourself with the normal Add / Nudge / Rotate operators. The optional ghost hint
(built in operators.py) shows translucent preview copies of a step's blocks when you're
stuck.

This file holds the data/plan helpers + the scene-state PropertyGroup; the operators and
the ghost rendering live in operators.py (they need the material/rotate helpers there).

bpy note: we CAN'T import manual/* — that package is the standalone generator and never
loads bpy. The two sides agree only on the JSON format. The couple of tiny things we need
from it (parse "WxD", canonical orientation-independent id) are reimplemented here.
"""

import json
import os
import re

import bpy

from . import constants, library


# --- Tiny block-id helpers (mirror manual/catalogue.py; can't import it — see module docstring)
_TYPE_RE = re.compile(r"^(\d+)x(\d+)$")


def parse_dims(type_id):
    """'4x2' -> (4, 2). Raises ValueError on a non-rectangular id (L / T / round / step)."""
    m = _TYPE_RE.match(type_id)
    if not m:
        raise ValueError(type_id)
    return int(m.group(1)), int(m.group(2))


def normalize_id(w, d):
    """Canonical, orientation-independent library id: a 1x4 placement is a '4x1' rotated."""
    return "{}x{}".format(max(w, d), min(w, d))


# --- Plan loading (memoised so per-frame panel redraws don't re-parse the file) ---
_PLAN_CACHE = {}   # filepath -> (mtime, plan dict)


def load_plan(path):
    """Read + lightly validate a build-plan JSON. Raises ValueError (friendly message)
    on anything malformed; the caller turns that into a clean self.report error."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)   # JSONDecodeError is a ValueError subclass — caller catches it
    if data.get("version") != 1:
        raise ValueError("this looks like a different file format (version {!r}, "
                         "expected 1).".format(data.get("version")))
    bags = data.get("bags")
    if not bags:
        raise ValueError("there are no bags/steps in this plan.")
    for bag in bags:
        for step in bag.get("steps", []):
            for block in step.get("add", []):
                if "cell" not in block or "type" not in block:
                    raise ValueError("a step has a block missing its 'cell' or 'type'.")
    return data


def invalidate_cache(path):
    _PLAN_CACHE.pop(path, None)


def get_plan(path):
    """Return the parsed plan for `path`, re-reading only when the file's mtime changes.
    Returns None if the file is gone or unreadable (the panel shows a 'reload' hint)."""
    if not path:
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cached = _PLAN_CACHE.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        plan = load_plan(path)
    except (ValueError, OSError):
        return None
    _PLAN_CACHE[path] = (mtime, plan)
    return plan


# --- Step addressing (the UI walks a single linear index across all bags) ---
def step_count(plan):
    return sum(len(bag.get("steps", [])) for bag in plan.get("bags", []))


def iter_steps(plan):
    """Yield (global_index, bag_index, step_in_bag, bag_name, step_dict), 0-based."""
    g = 0
    for bi, bag in enumerate(plan.get("bags", [])):
        bag_name = bag.get("name", "Bag {}".format(bi + 1))
        for si, step in enumerate(bag.get("steps", [])):
            yield (g, bi, si, bag_name, step)
            g += 1


def locate(plan, global_index):
    """(bag_index, step_in_bag, bag_name, step_dict) for a global step index, clamped
    into range. Returns (0, 0, '', {}) for an empty plan."""
    n = step_count(plan)
    if n == 0:
        return (0, 0, "", {})
    target = max(0, min(n - 1, global_index))
    for (g, bi, si, bag_name, step) in iter_steps(plan):
        if g == target:
            return (bi, si, bag_name, step)
    return (0, 0, "", {})


# --- Parts list (derived per step: count this step's blocks) ---
_FINISH_LABEL = {"stud": "studded", "smooth": "smooth"}


def parts_for_step(step):
    """A step's parts list as ['2× 2x2 Yellow (studded)', …], derived (never stored) by
    counting `add` by (canonical id, material, finish). Mirrors the manual's parts list."""
    counts = {}
    for block in step.get("add", []):
        type_id = block.get("type", "1x1")
        try:
            w, d = parse_dims(type_id)
            canonical = normalize_id(w, d)
        except ValueError:
            canonical = type_id   # non-rectangular: group by the raw type string
        material = block.get("material", "?")
        finish = block.get("finish", "stud")
        key = (canonical, material, finish)
        counts[key] = counts.get(key, 0) + 1
    lines = []
    for (canonical, material, finish), n in sorted(counts.items()):
        finish_label = _FINISH_LABEL.get(finish, finish)
        lines.append("{}× {} {} ({})".format(n, canonical, material, finish_label))
    return lines


# --- Honor-system checkoff (explicit, NOT inferred from the scene) ---
# Stored as a comma-separated string of global step indices on the scene state, so it's
# glass-box (visible/editable) and saved in the .blend.
def _checked_set(state):
    if not state.checked_steps:
        return set()
    return {int(x) for x in state.checked_steps.split(",") if x.strip()}


def is_checked(state, idx):
    return idx in _checked_set(state)


def toggle_checked(state, idx):
    s = _checked_set(state)
    s.discard(idx) if idx in s else s.add(idx)
    state.checked_steps = ",".join(str(i) for i in sorted(s))


def checked_count(state):
    return len(_checked_set(state))


# --- Bag collections + the "active bag" so hand-placed blocks land in the right one ---
def ensure_bag_collection(context, bag_name):
    """Get-or-create the collection for a bag, nested under 'SnapBlock Build'.

    bpy note: collection data-names are unique across the whole file, so we namespace the
    bag name (BAG_COLLECTION_PREFIX) to avoid colliding with some unrelated 'Walls'."""
    build = library.get_build_collection(context)
    name = constants.BAG_COLLECTION_PREFIX + bag_name
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    # Link under the build collection if it isn't already a child of it.
    if build.children.get(coll.name) is None:
        build.children.link(coll)
    return coll


def find_layer_collection(layer_coll, target):
    """Find the LayerCollection (the per-view-layer wrapper that carries 'active' state)
    that wraps the data-collection `target`, by recursing the layer-collection tree.

    bpy note: bpy.data.collections is the data; view_layer.layer_collection is a parallel
    tree of view-state wrappers. You make new objects land in a collection by setting the
    active *LayerCollection*, not the collection itself — hence this lookup."""
    if layer_coll.collection is target:
        return layer_coll
    for child in layer_coll.children:
        found = find_layer_collection(child, target)
        if found is not None:
            return found
    return None


def set_active_bag(context, bag_name):
    """Make `bag_name`'s collection the active one, so subsequently added blocks go there."""
    coll = ensure_bag_collection(context, bag_name)
    # bpy gotcha: a freshly linked collection's LayerCollection wrapper may not be in the
    # tree until the view layer refreshes — force it before searching.
    context.view_layer.update()
    lc = find_layer_collection(context.view_layer.layer_collection, coll)
    if lc is not None:
        context.view_layer.active_layer_collection = lc
    return coll


def current_target_collection(context):
    """Where a hand-placed block should be linked: the active bag's collection while a
    plan is loaded, else the plain 'SnapBlock Build' collection. Called by add_block."""
    state = getattr(context.scene, "snapblock_driver", None)
    if state is not None and state.plan_filepath:
        plan = get_plan(state.plan_filepath)
        if plan is not None:
            _bi, _si, bag_name, _step = locate(plan, state.global_index)
            if bag_name:
                return ensure_bag_collection(context, bag_name)
    return library.get_build_collection(context)


# --- Ghost mapping: a plan's as-placed "WxD" -> library object + rotation ---
def ghost_spec(block):
    """(library_id, rotation_steps) for a plan block.

    A plan `type` "WxD" means W cells along X, D along Y (matches the PDF renderer). The
    library stocks one orientation per rectangle, named big×small ("4x2") and *authored
    with the long side along Y* (the "4x2" object is physically 2 wide in X, 4 deep in Y).
    So `normalize_id(w,d)` is the object to append, and it needs a 90° turn exactly when
    the placement's long side runs along X instead — i.e. when w > d. Non-rectangular
    types append unrotated (orientation refinement is deferred)."""
    type_id = block.get("type", "1x1")
    try:
        w, d = parse_dims(type_id)
    except ValueError:
        return type_id, 0
    return normalize_id(w, d), (1 if w > d else 0)


class SNAPBLOCK_driver_state(bpy.types.PropertyGroup):
    """Per-scene driver state. A PropertyGroup is Blender's serializable struct: it's
    saved in the .blend and visible/editable, so progress is glass-box and survives a
    reload. Attached to every Scene as scene.snapblock_driver in __init__.py."""
    plan_filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    model_name: bpy.props.StringProperty()
    global_index: bpy.props.IntProperty(default=0, min=0)
    show_ghost: bpy.props.BoolProperty(default=False)
    # Honor-system checkoff: comma-separated global step indices (see _checked_set).
    checked_steps: bpy.props.StringProperty(default="")


classes = (
    SNAPBLOCK_driver_state,
)
