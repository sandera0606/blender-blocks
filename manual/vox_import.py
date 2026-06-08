"""
Load a voxel model — either a hand-authored voxel JSON or a MagicaVoxel `.vox` binary.

Voxel-model shape (what the planner consumes):
    {
      "name": "...",
      "grid": {"U": 1.0, "H": 1.0},
      "palette": { "Green": [r,g,b], ... },   # 0..1
      "cells":   [ {"cell": [x,y,z], "material": "Green"}, ... ],
      "overrides": { "Green": "smooth" | "studded" }   # optional
    }

The `.vox` parser is hand-rolled (the format is a tiny chunked binary) so there's no
extra dependency. An optional sidecar JSON can rename colours and set finish overrides.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path


def load_voxel(path, overrides_path=None) -> dict:
    path = Path(path)
    if path.suffix.lower() == ".vox":
        model = _from_vox(path)
    else:
        model = json.loads(path.read_text(encoding="utf-8"))
    if overrides_path:
        _apply_sidecar(model, json.loads(Path(overrides_path).read_text(encoding="utf-8")))
    return model


# --- MagicaVoxel .vox ------------------------------------------------------------

def _from_vox(path: Path) -> dict:
    data = path.read_bytes()
    if data[:4] != b"VOX ":
        raise ValueError(f"{path} is not a MagicaVoxel .vox file")

    voxels = []          # (x, y, z, color_index)
    palette = None       # list of 256 (r,g,b,a) ints, index 0..255

    pos = 8              # skip 'VOX ' + version int
    # MAIN chunk header
    _id, content_n, _children_n = _chunk_header(data, pos)
    pos += 12 + content_n   # MAIN has no content; step into its children
    end = len(data)
    while pos < end:
        cid, content_n, children_n = _chunk_header(data, pos)
        body = pos + 12
        content = data[body:body + content_n]
        if cid == b"XYZI":
            (n,) = struct.unpack_from("<i", content, 0)
            for k in range(n):
                x, y, z, ci = struct.unpack_from("<BBBB", content, 4 + k * 4)
                voxels.append((x, y, z, ci))
        elif cid == b"RGBA":
            palette = [struct.unpack_from("<BBBB", content, j * 4) for j in range(256)]
        pos = body + content_n + children_n

    if palette is None:
        # Modern MagicaVoxel always writes RGBA; only old files miss it. Deterministic
        # fallback so the import still works (colours won't match the editor exactly).
        palette = _fallback_palette()

    # Map used colour indices -> materials. MagicaVoxel: voxel colour index i (1..255)
    # maps to palette entry i-1.
    used = sorted({ci for (_, _, _, ci) in voxels})
    pal_out, name_of = {}, {}
    for ci in used:
        r, g, b, _a = palette[(ci - 1) % 256]
        name = f"C{ci}"
        name_of[ci] = name
        pal_out[name] = [round(r / 255.0, 4), round(g / 255.0, 4), round(b / 255.0, 4)]

    cells = [{"cell": [x, y, z], "material": name_of[ci]} for (x, y, z, ci) in voxels]
    return {
        "name": path.stem,
        "grid": {"U": 1.0, "H": 1.0},
        "palette": pal_out,
        "cells": cells,
        # keep the colour index in materials so a sidecar can target "C12"
    }


def _chunk_header(data, pos):
    cid = data[pos:pos + 4]
    content_n, children_n = struct.unpack_from("<ii", data, pos + 4)
    return cid, content_n, children_n


def _fallback_palette():
    """A deterministic spread of distinct colours when a .vox has no RGBA chunk."""
    pal = []
    for i in range(256):
        # simple HSV-ish ramp; good enough to distinguish materials
        h = (i * 47) % 256
        pal.append((h, (h * 3) % 256, (255 - h) % 256, 255))
    return pal


# --- sidecar overrides -----------------------------------------------------------

def _apply_sidecar(model, sidecar):
    """Rename materials and set finish overrides from a sidecar:
        { "colors": { "C12": {"name": "Water", "finish": "smooth"} } }
    Keys match the material names produced above (e.g. "C12") or any hand-authored name.
    """
    colors = sidecar.get("colors", sidecar)
    rename = {}
    overrides = model.setdefault("overrides", {})
    for key, spec in colors.items():
        new_name = spec.get("name", key)
        if new_name != key:
            rename[key] = new_name
        if "finish" in spec:
            overrides[new_name] = spec["finish"]

    if rename:
        model["palette"] = {rename.get(n, n): rgb for n, rgb in model["palette"].items()}
        for cell in model["cells"]:
            cell["material"] = rename.get(cell["material"], cell["material"])
