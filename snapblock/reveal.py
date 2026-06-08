"""
SnapBlock "reveal" mode — the trainer-wheels payoff.

When the user turns on "Show me what's really happening" (scene.snapblock_reveal),
the add-on surfaces the real Blender concepts behind each action. Three parts live
across the add-on:

  1. Expanded tooltips — operators' dynamic description() classmethods (operators.py).
  2. A concept glossary subpanel — SNAPBLOCK_PT_glossary (panels.py), using CONCEPTS below.
  3. A "What just happened" subpanel — SNAPBLOCK_PT_lastaction (panels.py), showing a
     short explanation of the last action, set here via note().

This module owns the shared glossary text (CONCEPTS) and the last-action note.
"""

import bpy

# Plain-English definitions for the glossary subpanel. The 8 terms the brief asks
# for, in the order a beginner meets them.
CONCEPTS = (
    ("Object", "A single thing in your scene — like one block. Everything you add is an object."),
    ("Mesh", "The shape of an object: its points, edges and faces. The object is the 'thing'; the mesh is its form."),
    ("Material", "How a surface looks — its color and finish. A block gets one when you pick a color."),
    ("Collection", "A named folder for objects. Your blocks live in the 'SnapBlock Build' collection."),
    ("Outliner", "The list in the top-right corner showing every object and collection in your scene."),
    ("Properties Panel", "The tabs on the right with detailed settings for the selected object and its material."),
    ("Modifier", "A non-destructive effect stacked on a mesh (like Bevel or Array). None are used yet — just good to know the word."),
    ("Origin Point", "The small dot marking an object's position. Moving an object moves its origin."),
)


# --- Last-action note ------------------------------------------------------
# A short explanation of the most recent action. Operators set it via note();
# the "What just happened" subpanel reads it via get_note() and shows it (only
# when reveal mode is on). Module state, like the glossary text — it's transient
# presentation, not scene data, so it deliberately isn't saved in the .blend.
_note = {"text": ""}


def note(text):
    """Record `text` as the explanation of the last action, and refresh the
    sidebar so the panel shows it right away. Operators call this after an action
    when reveal mode is on (they do the toggle check)."""
    _note["text"] = text
    _tag_sidebar_redraws()


def get_note():
    """The last-action explanation, or "" if there hasn't been one yet."""
    return _note["text"]


def _tag_sidebar_redraws():
    """Nudge the N-panel to redraw so a new note appears without the user having
    to mouse over the sidebar. The operator's own button click usually triggers a
    redraw anyway; this just makes it reliable (e.g. for the arrow-key nudge)."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'UI':
                        region.tag_redraw()


def register():
    """Nothing to register — the note is plain module state and the panel is a
    normal class. Kept so __init__ can call reveal.register()/unregister()
    symmetrically alongside the other modules."""
    pass


def unregister():
    _note["text"] = ""
