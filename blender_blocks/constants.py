"""
Blender Blocks constants — the single home for all magic numbers and presets.

Nothing else in the add-on should hardcode grid sizes, names, or colors; import
from here so there's one place to change them.
"""

# --- Grid ------------------------------------------------------------------
# One grid cell = 1.0 Blender unit. The blocks are authored at 2.0 BU/cell, but
# build_library.py halves them so a cell equals one native Blender unit — that way
# Blender's default grid and increment-snap (which step by 1.0) line up with cells,
# and a block at cell (gx, gy, gz) sits at world (gx, gy, gz). Placements are stored
# as integer grid coords and converted to world coords as (gx*U, gy*U, gz*H).
U = 1.0   # cell size on X and Y, in Blender units
H = 1.0   # block body height on Z (one cell). Studs add a little on top.

# How close a captured block's footprint must be to a whole number of cells to count
# as "on the grid". Tight enough to refuse a visibly off-grid block, loose enough to
# absorb float noise from baking an object's world transform into its mesh.
GRID_SNAP_TOL = 1e-4

# --- Names / UI ------------------------------------------------------------
ADDON_CATEGORY = "Blender Blocks"            # the N-panel tab name
BUILD_COLLECTION = "Blender Blocks Build"    # collection placed blocks go into
LIBRARY_FILENAME = "blender_blocks_library.blend"   # bundled block library

# Custom blocks the user captures from a selection live OUTSIDE the package (so an
# add-on reinstall can't wipe them), one .blend per block, under this subpath of
# Blender's per-user CONFIG dir (resolved via bpy.utils.user_resource in prefs.py).
CUSTOM_BLOCKS_DIRNAME = "blender_blocks/custom_blocks"

# --- Follow-a-manual driver ------------------------------------------------
# Each "bag" in a build plan becomes a collection nested under BUILD_COLLECTION.
# Data-block names are file-global, so bag names are namespaced with this prefix
# to avoid colliding with unrelated collections.
BAG_COLLECTION_PREFIX = "Blender Blocks: "
# The ghost hint's throwaway collection + its translucent material. Cleared whenever
# the hint is toggled off or the step changes — it's a hint, not part of the build.
GHOST_COLLECTION = "Blender Blocks Ghost (hint)"
GHOST_MATERIAL = "Ghost"
GHOST_COLOR = (0.55, 0.6, 0.7)   # cool grey, clearly "not a real block"
GHOST_OPACITY = 0.25             # translucent so the real build reads through it

# --- Block catalogue -------------------------------------------------------
# The BUILT-IN block types. (type_id, display_label). type_id must match an object
# name in the bundled library .blend; placed blocks are named "Block_<type_id>.NNN".
# Ordered small -> large. Custom blocks the user captures are NOT listed here — they
# live in prefs; prefs.iter_blocks() yields these built-ins followed by the custom
# ones, so the panel shows both from one source of truth.
# Footprint sizes (in cells) are deliberately omitted until the rotation/
# orientation question is settled — see tools/check_rotation.py.
BLOCK_TYPES = (
    ("1x1",        "1×1"),
    ("1x1_round",  "1×1 round"),
    ("2x1",        "2×1"),
    ("2x2",        "2×2"),
    ("2x2_round",  "2×2 round"),
    ("3x1",        "3×1"),
    ("3x2",        "3×2"),
    ("4x1",        "4×1"),
    ("4x2",        "4×2"),
    ("4x2_smooth", "4×2 smooth"),
    ("6x1",        "6×1"),
    ("8x2",        "8×2"),
    ("step",       "Step"),
    ("L",          "L-block"),
    ("T",          "T-block"),
    ("10x2",       "10×2"),
    ("10x4",       "10×4"),
    ("10x8",       "10×8"),
    ("10x10",      "10×10"),
    ("20x10",      "20×10"),
    ("20x20",      "20×20"),
)

# --- Materials -------------------------------------------------------------
# One material per color, named "BlenderBlocks_<colorname>", Principled BSDF only.
MATERIAL_PREFIX = "BlenderBlocks_"
MATERIAL_ROUGHNESS = 0.4     # plastic-ish — not glossy, not flat
MATERIAL_SUBSURFACE = 0.1    # a touch of subsurface for a plastic feel

# --- Color presets ---------------------------------------------------------
# (name, (r, g, b, a)). Applied later as Principled BSDF base color on a
# material named "BlenderBlocks_<name>". Values are friendly sRGB-ish picks.
# These are the built-in materials; the user can add their own (see prefs.py).
COLOR_PRESETS = (
    ("White",  (0.90, 0.90, 0.90, 1.0)),
    ("Black",  (0.02, 0.02, 0.02, 1.0)),
    ("Red",    (0.70, 0.05, 0.05, 1.0)),
    ("Orange", (0.85, 0.35, 0.03, 1.0)),
    ("Yellow", (0.85, 0.65, 0.05, 1.0)),
    ("Green",  (0.10, 0.50, 0.12, 1.0)),
    ("Blue",   (0.05, 0.15, 0.60, 1.0)),
    ("Gray",   (0.30, 0.30, 0.30, 1.0)),
)

# --- Finish presets --------------------------------------------------------
# Seeds for a custom material's look. (id, label, roughness, opacity, transmission).
# Picking a finish in the Add Material dialog copies these into the fine-tune
# sliders; the slider values are what actually get stored, so a finish is just a
# convenient starting point.
#   Matte       - solid, soft plastic
#   Glossy      - solid, shiny plastic
#   Translucent - frosted / see-through via alpha (opacity < 1)
#   Clear       - clear plastic / glass via transmission (needs raytracing in EEVEE)
FINISH_PRESETS = (
    ("MATTE",       "Matte",       0.6,  1.0, 0.0),
    ("GLOSSY",      "Glossy",      0.15, 1.0, 0.0),
    ("TRANSLUCENT", "Translucent", 0.4,  0.5, 0.0),
    ("CLEAR",       "Clear",       0.05, 1.0, 1.0),
)
