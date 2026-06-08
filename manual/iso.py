"""
Isometric drawing — the visual heart of the manual.

Reproduces the reference nanoblock idioms: new blocks HOVER above their slots on thin
dashed drop-lines; built blocks fade PALE; studs sit on exposed tops; smooth blocks have
none. Blocks are rectangular (W x D x 1). Everything is an axis-aligned box, so cubes,
rectangular blocks and studs all share `_box_faces`.

Draws onto a ReportLab canvas (lazy Color import). Math is y-DOWN; converted to the
y-UP PDF page at draw time via the caller's origin.
"""

from __future__ import annotations

# --- Projection (2:1 isometric). Base sizes at s=1; callers pass s to resize. ---
TILE_W = 11.0
TILE_H = 6.0
CUBE_H = 12.0

HOVER_CELLS = 1.7        # how far above its slot a new block floats
STUD_INSET = 0.30        # stud footprint inset from the cell edge (each side)
STUD_HEIGHT = 0.30       # stud height in cells

_SHADE = {"top": 1.00, "right": 0.82, "left": 0.66}
_FADE = 0.62             # how far built blocks blend toward white


def _corner(gx, gy, gz, s):
    return ((gx - gy) * TILE_W * s, (gx + gy) * TILE_H * s - gz * CUBE_H * s)


def _box_faces(x0, y0, z0, x1, y1, z1, s):
    """The three visible faces of an axis-aligned box, as point lists (y-down)."""
    def p(cx, cy, cz):
        return _corner(cx, cy, cz, s)
    top = [p(x0, y0, z1), p(x1, y0, z1), p(x1, y1, z1), p(x0, y1, z1)]
    right = [p(x1, y0, z0), p(x1, y1, z0), p(x1, y1, z1), p(x1, y0, z1)]
    left = [p(x0, y1, z0), p(x1, y1, z0), p(x1, y1, z1), p(x0, y1, z1)]
    return (("top", top), ("right", right), ("left", left))


def _shade(rgb, k):
    return tuple(min(1.0, max(0.0, c * k)) for c in rgb)


def _fade(rgb):
    return tuple(c + (1.0 - c) * _FADE for c in rgb)


def painter_order(blocks):
    """Back-to-front order for axis-aligned blocks viewed from the +X+Y+Z corner."""
    return sorted(blocks, key=lambda b: (b.x + b.y, b.z))


def _Color():
    from reportlab.lib.colors import Color
    return Color


def _poly(c, pts, fill, stroke, lw):
    Color = _Color()
    c.setFillColor(Color(*fill))
    c.setStrokeColor(Color(*stroke))
    c.setLineWidth(lw)
    path = c.beginPath()
    path.moveTo(*pts[0])
    for vx, vy in pts[1:]:
        path.lineTo(vx, vy)
    path.close()
    c.drawPath(path, stroke=1, fill=1)


def _draw_box(c, origin, faces_box, rgb, *, faded):
    ox, oy = origin
    base = _fade(rgb) if faded else rgb
    for name, face in faces_box:
        fill = _shade(base, _SHADE[name])
        if faded:
            stroke = _shade(base, _SHADE[name] * 0.92)
            lw = 0.4
        else:
            stroke = (0.13, 0.13, 0.13)
            lw = 0.7
        _poly(c, [(ox + px, oy - py) for px, py in face], fill, stroke, lw)


def _draw_body(c, origin, b, rgb, s, *, faded, dz=0.0):
    """Draw a rectangular block body (no studs). `dz` raises it (cells) for the hover."""
    z0, z1 = b.z + dz, b.z + 1 + dz
    _draw_box(c, origin, _box_faces(b.x, b.y, z0, b.x + b.width, b.y + b.depth, z1, s), rgb, faded=faded)


def _draw_stud(c, origin, cx, cy, ztop, rgb, s, *, faded):
    """Draw one stud (small box) sitting on top face height `ztop`."""
    sx0, sy0 = cx + STUD_INSET, cy + STUD_INSET
    sx1, sy1 = cx + 1 - STUD_INSET, cy + 1 - STUD_INSET
    _draw_box(c, origin, _box_faces(sx0, sy0, ztop, sx1, sy1, ztop + STUD_HEIGHT, s), rgb, faded=faded)


def _draw_group(c, origin, blocks, palette, s, *, faded, dz=0.0):
    """Draw a set of blocks: ALL bodies first (back-to-front), THEN all studs
    (back-to-front). Two passes so no block body can paint over another block's
    stud — studs always sit on top of every body."""
    for b in painter_order(blocks):
        _draw_body(c, origin, b, palette[b.material], s, faded=faded, dz=dz)
    studs = []
    for b in blocks:
        for (cx, cy) in b.studs:
            # depth key includes z so studs on taller blocks draw in front
            studs.append((cx + cy + b.z, cx, cy, b.z + 1 + dz, palette[b.material]))
    studs.sort(key=lambda t: t[0])
    for (_key, cx, cy, ztop, rgb) in studs:
        _draw_stud(c, origin, cx, cy, ztop, rgb, s, faded=faded)


def _drop_line(c, origin, b, s):
    Color = _Color()
    ox, oy = origin
    cx, cy = b.x + b.width / 2.0, b.y + b.depth / 2.0
    x_top, y_top = _corner(cx, cy, b.z + HOVER_CELLS, s)
    x_bot, y_bot = _corner(cx, cy, b.z, s)
    c.setStrokeColor(Color(0.45, 0.45, 0.45))
    c.setLineWidth(0.5)
    c.setDash(1.4, 1.6)
    c.line(ox + x_top, oy - y_top, ox + x_bot, oy - y_bot)
    c.setDash()


def bounds(blocks, s, *, hover_cells=None):
    hover_cells = hover_cells or set()
    xs, ys = [], []
    for b in blocks:
        extra = HOVER_CELLS if b.cell in hover_cells else 0.0
        for cx in (b.x, b.x + b.width):
            for cy in (b.y, b.y + b.depth):
                for cz in (b.z, b.z + 1):
                    px, py = _corner(cx, cy, cz + extra, s)
                    xs.append(px); ys.append(py)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def fit_scale(blocks, area_w, area_h, *, hover_cells=None, fill=0.86, max_scale=3.5):
    bx0, by0, bx1, by1 = bounds(blocks, 1.0, hover_cells=hover_cells)
    w = max(bx1 - bx0, 1e-6)
    h = max(by1 - by0, 1e-6)
    return min(max_scale, (area_w / w) * fill, (area_h / h) * fill)


def draw_diagram(c, rect, cumulative, new_cells, palette):
    """Draw the build-so-far in page rect (x0,y0,x1,y1, y-up). Blocks whose origin cell
    is in `new_cells` hover full-colour on drop-lines; the rest are pale context. With
    `new_cells` empty (cover / finished) everything is full colour."""
    x0, y0, x1, y1 = rect
    area_w, area_h = x1 - x0, y1 - y0
    s = fit_scale(cumulative, area_w, area_h, hover_cells=new_cells)

    bx0, by0, bx1, by1 = bounds(cumulative, s, hover_cells=new_cells)
    ox = x0 + (area_w - (bx1 - bx0)) / 2.0 - bx0
    oy = y1 - (area_h - (by1 - by0)) / 2.0 + by0

    highlight = bool(new_cells)
    base = [b for b in cumulative if not (highlight and b.cell in new_cells)]
    new = [b for b in cumulative if highlight and b.cell in new_cells]

    _draw_group(c, (ox, oy), base, palette, s, faded=highlight)
    for b in new:
        _drop_line(c, (ox, oy), b, s)
    _draw_group(c, (ox, oy), new, palette, s, faded=False, dz=HOVER_CELLS)


def draw_part_icon(c, center, w, d, finish, palette_rgb, size):
    """A small iso block (w x d, with studs if studded) centred at page point `center`."""
    studs = tuple((i, j) for i in range(w) for j in range(d)) if finish == "stud" else ()
    icon = _IconBlock(w, d, finish, studs)
    bx0, by0, bx1, by1 = bounds([icon], size)
    cx, cy = center
    ox = cx - (bx0 + bx1) / 2.0
    oy = cy + (by0 + by1) / 2.0
    _draw_body(c, (ox, oy), icon, palette_rgb, size, faded=False)
    for (i, j) in sorted(studs, key=lambda ij: ij[0] + ij[1]):
        _draw_stud(c, (ox, oy), i, j, 1.0, palette_rgb, size, faded=False)


class _IconBlock:
    """A standalone block at the origin for sizing/drawing parts-list icons."""
    def __init__(self, w, d, finish, studs):
        self.x = self.y = self.z = 0
        self.width, self.depth, self.finish, self.studs = w, d, finish, studs

    @property
    def cell(self):
        return (0, 0, 0)


def icon_width(w, d, size):
    """Page width a parts-list icon of this footprint will occupy."""
    bx0, _, bx1, _ = bounds([_IconBlock(w, d, "stud", ())], size)
    return bx1 - bx0
