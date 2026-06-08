"""
Isometric cube drawing — the visual heart of the manual.

Redesigned to match the reference nanoblock booklets in ./references/. The signature
idioms reproduced here:

  - new blocks for a step HOVER above their slots, joined by thin vertical drop-lines
    that show exactly which column each one drops into;
  - already-built blocks are drawn in a PALE faded tint (build context);
  - little iso block icons (with ×counts) for the per-step parts list.

Draws onto a ReportLab canvas passed in; the only ReportLab use is a lazy Color import,
so the module stays light. Math is done in a y-DOWN space and converted to the y-UP PDF
page at draw time (origin passed by the caller).
"""

from __future__ import annotations

# --- Projection (2:1 isometric). Base sizes at scale s=1; callers pass s to resize. ---
TILE_W = 11.0    # half-width of a cell
TILE_H = 6.0     # half-depth of a cell (the ground-plane "squash")
CUBE_H = 12.0    # on-screen height of one cell of Z

HOVER_CELLS = 1.7   # how far above its slot a new block floats

# Face shading: top brightest, then right, then left.
_SHADE = {"top": 1.00, "right": 0.82, "left": 0.66}
_FADE = 0.62        # how far faded (built) blocks blend toward white (0=none, 1=white)


def _corner(gx, gy, gz, s):
    """Project a grid corner to 2D (y-down)."""
    return ((gx - gy) * TILE_W * s, (gx + gy) * TILE_H * s - gz * CUBE_H * s)


def _faces(gx, gy, gz, s):
    """The three visible faces of the unit cube at cell (gx,gy,gz), as point lists."""
    def p(cx, cy, cz):
        return _corner(cx, cy, cz, s)
    top = [p(gx, gy, gz + 1), p(gx + 1, gy, gz + 1), p(gx + 1, gy + 1, gz + 1), p(gx, gy + 1, gz + 1)]
    right = [p(gx + 1, gy, gz), p(gx + 1, gy + 1, gz), p(gx + 1, gy + 1, gz + 1), p(gx + 1, gy, gz + 1)]
    left = [p(gx, gy + 1, gz), p(gx + 1, gy + 1, gz), p(gx + 1, gy + 1, gz + 1), p(gx, gy + 1, gz + 1)]
    return (("top", top), ("right", right), ("left", left))


def _shade(rgb, k):
    return tuple(min(1.0, max(0.0, c * k)) for c in rgb)


def _fade(rgb):
    return tuple(c + (1.0 - c) * _FADE for c in rgb)


def painter_order(blocks):
    """Back-to-front order for axis-aligned cubes viewed from the +X+Y+Z corner."""
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


def _draw_cube(c, origin, gx, gy, gz, rgb, s, *, faded, dz=0.0):
    """Draw one cube. `dz` raises it (in cells) for the hover effect."""
    ox, oy = origin
    base = _fade(rgb) if faded else rgb
    for name, face in _faces(gx, gy, gz + dz, s):
        fill = _shade(base, _SHADE[name])
        if faded:
            stroke = _shade(base, _SHADE[name] * 0.92)
            lw = 0.4
        else:
            stroke = (0.13, 0.13, 0.13)
            lw = 0.7
        pts = [(ox + px, oy - py) for px, py in face]
        _poly(c, pts, fill, stroke, lw)


def _drop_line(c, origin, gx, gy, gz, s):
    """Thin vertical guide from a hovered block down to its resting slot."""
    Color = _Color()
    ox, oy = origin
    cx, cy = gx + 0.5, gy + 0.5
    x_top, y_top = _corner(cx, cy, gz + HOVER_CELLS, s)   # bottom of the hovered cube
    x_bot, y_bot = _corner(cx, cy, gz, s)                 # the slot it lands in
    c.setStrokeColor(Color(0.45, 0.45, 0.45))
    c.setLineWidth(0.5)
    c.setDash(1.4, 1.6)
    c.line(ox + x_top, oy - y_top, ox + x_bot, oy - y_bot)
    c.setDash()  # reset


def bounds(blocks, s, *, hover_cells=None):
    """(minx,miny,maxx,maxy) extent in y-down space. `hover_cells` is a set of cell keys
    drawn raised, so their hovered tops are included and nothing clips."""
    hover_cells = hover_cells or set()
    xs, ys = [], []
    for b in blocks:
        extra = HOVER_CELLS if b.cell in hover_cells else 0.0
        for cx in (b.x, b.x + 1):
            for cy in (b.y, b.y + 1):
                for cz in (b.z, b.z + 1):
                    px, py = _corner(cx, cy, cz + extra, s)
                    xs.append(px); ys.append(py)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def fit_scale(blocks, area_w, area_h, *, hover_cells=None, fill=0.86, max_scale=1.4):
    """Pick a scale so the diagram fits `area_w` x `area_h` with a little margin."""
    bx0, by0, bx1, by1 = bounds(blocks, 1.0, hover_cells=hover_cells)
    w = max(bx1 - bx0, 1e-6)
    h = max(by1 - by0, 1e-6)
    return min(max_scale, (area_w / w) * fill, (area_h / h) * fill)


def draw_diagram(c, rect, cumulative, new_cells, palette):
    """Draw the build-so-far inside page rect (x0,y0,x1,y1, y-up).

    Blocks not in `new_cells` are pale context. New blocks float (with drop-lines) and
    are full colour. If `new_cells` is empty (cover / finished page), everything is drawn
    full colour. Auto-scales to fit the rect.
    """
    x0, y0, x1, y1 = rect
    area_w, area_h = x1 - x0, y1 - y0
    s = fit_scale(cumulative, area_w, area_h, hover_cells=new_cells)

    bx0, by0, bx1, by1 = bounds(cumulative, s, hover_cells=new_cells)
    # Centre the diagram in the rect. (y-down bounds -> y-up page: oy aligns the top.)
    ox = x0 + (area_w - (bx1 - bx0)) / 2.0 - bx0
    oy = y1 - (area_h - (by1 - by0)) / 2.0 + by0

    highlight = bool(new_cells)
    base = [b for b in cumulative if not (highlight and b.cell in new_cells)]
    new = [b for b in cumulative if highlight and b.cell in new_cells]

    # 1) faded context
    for b in painter_order(base):
        _draw_cube(c, (ox, oy), b.x, b.y, b.z, palette[b.material], s, faded=True)
    # 2) drop-lines under the hovered blocks
    for b in new:
        _drop_line(c, (ox, oy), b.x, b.y, b.z, s)
    # 3) hovered new blocks, full colour
    for b in painter_order(new):
        _draw_cube(c, (ox, oy), b.x, b.y, b.z, palette[b.material], s, faded=False, dz=HOVER_CELLS)


def draw_part_icon(c, center, rgb, size):
    """A single small iso cube centred at page point `center`, for the parts list."""
    cx, cy = center
    s = size
    # One cube; centre its projected bounds on (cx, cy).
    bx0, by0, bx1, by1 = bounds([_FakeCell(0, 0, 0)], s)
    ox = cx - (bx0 + bx1) / 2.0
    oy = cy + (by0 + by1) / 2.0
    _draw_cube(c, (ox, oy), 0, 0, 0, rgb, s, faded=False)


class _FakeCell:
    """Tiny stand-in so bounds() can size a single icon cube."""
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z

    @property
    def cell(self):
        return (self.x, self.y, self.z)
