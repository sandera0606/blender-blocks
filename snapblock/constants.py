"""
SnapBlock constants — the single home for all magic numbers and presets.

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

# --- Names / UI ------------------------------------------------------------
ADDON_CATEGORY = "SnapBlock"            # the N-panel tab name
BUILD_COLLECTION = "SnapBlock Build"    # collection placed blocks go into
LIBRARY_FILENAME = "snapblock_library.blend"   # bundled block library

# --- Block catalogue -------------------------------------------------------
# (type_id, display_label). type_id must match an object name in the library
# .blend; placed blocks are named "Block_<type_id>.NNN". Ordered small -> large.
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
# One material per color, named "SnapBlock_<colorname>", Principled BSDF only.
MATERIAL_PREFIX = "SnapBlock_"
MATERIAL_ROUGHNESS = 0.4     # plastic-ish — not glossy, not flat
MATERIAL_SUBSURFACE = 0.1    # a touch of subsurface for a plastic feel

# --- Color presets ---------------------------------------------------------
# (name, (r, g, b, a)). Applied later as Principled BSDF base color on a
# material named "SnapBlock_<name>". Values are friendly sRGB-ish picks.
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
