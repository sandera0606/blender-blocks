"""
SnapBlock operators.

v0.1 scaffold: only a placeholder operator so the panel buttons are clickable
while the panel layout is verified. Real operators (add block, apply color,
toggle reveal details) land in the next steps.

bpy note: every user action in Blender is a bpy.types.Operator. The class needs
a unique bl_idname in the form "category.action" (lowercase, one dot); that's
the string the UI calls via layout.operator("snapblock.placeholder").
"""

import bpy


class SNAPBLOCK_OT_placeholder(bpy.types.Operator):
    """Stand-in for a not-yet-wired button. Reports a friendly message."""
    bl_idname = "snapblock.placeholder"
    bl_label = "SnapBlock (coming soon)"
    bl_description = "This isn't wired up yet — it arrives in the next step"
    bl_options = {'INTERNAL'}

    # Operators carry their own properties (bpy.props), set by the button that
    # calls them. Here it just lets each button say what it would have done.
    info: bpy.props.StringProperty(default="This button")

    def execute(self, context):
        # self.report puts a message in the status bar / info log — the
        # friendly, no-traceback way to talk to the user.
        self.report({'INFO'}, "{} isn't wired up yet — coming next step.".format(self.info))
        return {'FINISHED'}


# Each module exposes a `classes` tuple; __init__.py collects them for
# registration. Order matters: classes a panel references must register first,
# which is why operators register before panels.
classes = (
    SNAPBLOCK_OT_placeholder,
)
