"""
Load and walk a build-plan (see ../docs/build_plan.md).

Pure standard library + the local catalogue — no Blender, no drawing deps. This module
is the shared understanding of the format: load it, validate it lightly, and iterate it
as a sequence of per-step "views" the renderer can draw one page from.

Blocks may be rectangular (W x D x 1) and carry a finish (studded / smooth). Which of a
studded block's cells actually *show* a stud is NOT stored — it depends on what's been
stacked so far, so it's computed per step from cumulative occupancy (see `occupancy` and
`iso.visible_studs`). A stud is drawn only while its cell's top is still exposed.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import catalogue


@dataclass(frozen=True)
class Block:
    x: int
    y: int
    z: int
    width: int = 1
    depth: int = 1
    type: str = "1x1"            # as-placed "WxD"
    material: str = ""
    finish: str = "stud"          # "stud" | "smooth"

    @property
    def cell(self):
        return (self.x, self.y, self.z)

    @property
    def footprint(self):
        return [(self.x + i, self.y + j) for i in range(self.width) for j in range(self.depth)]

    @property
    def cells(self):
        """The filled (x, y, z) cells this block occupies (height 1)."""
        return [(self.x + i, self.y + j, self.z)
                for i in range(self.width) for j in range(self.depth)]

    @property
    def catalogue_id(self):
        """Orientation-independent library id (1x4 and 4x1 share '4x1')."""
        return catalogue.normalize_id(self.width, self.depth)


@dataclass
class Part:
    """A line in a step's parts list: how many of one (catalogue_id, material, finish)."""
    count: int
    type: str          # catalogue id, e.g. "4x1"
    width: int
    depth: int
    material: str
    finish: str


@dataclass
class StepView:
    bag_index: int
    bag_name: str
    step_in_bag: int
    step_global: int
    total_steps: int
    cumulative: list
    new: list
    parts: list


@dataclass
class Plan:
    name: str
    grid_u: float
    grid_h: float
    palette: dict
    bags: list = field(default_factory=list)


class PlanError(ValueError):
    """A build plan that doesn't conform to the format."""


def _block_from_dict(b: dict) -> Block:
    type_id = b.get("type", "1x1")
    try:
        w, d = catalogue.parse_dims(type_id)
    except ValueError:
        raise PlanError(f"block has non-rectangular type {type_id!r}; only WxD supported")
    cx, cy, cz = b["cell"]
    finish = b.get("finish", "stud")
    # A legacy "studs" array (old plans) is intentionally ignored: stud visibility is now
    # derived per step from occupancy, not stored. `finish` is all the renderer needs.
    return Block(x=cx, y=cy, z=cz, width=w, depth=d, type=type_id,
                 material=b["material"], finish=finish)


def load_plan(path) -> Plan:
    return plan_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def plan_from_dict(data: dict) -> Plan:
    if data.get("version") != 1:
        raise PlanError(f"unsupported build-plan version: {data.get('version')!r} (this tool reads 1)")

    palette = {name: tuple(rgb) for name, rgb in (data.get("palette") or {}).items()}
    plan = Plan(
        name=(data.get("model") or {}).get("name", "Untitled"),
        grid_u=(data.get("grid") or {}).get("U", 1.0),
        grid_h=(data.get("grid") or {}).get("H", 1.0),
        palette=palette,
        bags=data.get("bags") or [],
    )

    # Light validation: every referenced material must exist in the palette.
    for bag in plan.bags:
        for step in bag.get("steps", []):
            for b in step.get("add", []):
                if b.get("material") not in palette:
                    raise PlanError(
                        f"block at cell {b.get('cell')} uses material "
                        f"{b.get('material')!r}, which isn't in the palette")
    return plan


def occupancy(blocks) -> set:
    """Every filled (x, y, z) cell covered by `blocks` (each block is height 1).

    Stud visibility is read off this: a studded block shows a stud on (cx, cy, z) iff
    (cx, cy, z+1) is not in the occupancy at that step (nothing stacked on it yet)."""
    occ = set()
    for b in blocks:
        occ.update(b.cells)
    return occ


def _parts(blocks) -> list:
    counts = Counter((b.catalogue_id, b.material, b.finish) for b in blocks)
    dims = {b.catalogue_id: (max(b.width, b.depth), min(b.width, b.depth)) for b in blocks}
    out = []
    for (cid, mat, finish), n in sorted(counts.items()):
        w, d = dims[cid]
        out.append(Part(count=n, type=cid, width=w, depth=d, material=mat, finish=finish))
    return out


def iter_steps(plan: Plan):
    total = sum(len(bag.get("steps", [])) for bag in plan.bags)
    cumulative = []
    step_global = 0
    for bag_index, bag in enumerate(plan.bags):
        bag_name = bag.get("name", f"Bag {bag_index + 1}")
        for step_in_bag, step in enumerate(bag.get("steps", []), start=1):
            step_global += 1
            new = [_block_from_dict(b) for b in step.get("add", [])]
            cumulative = cumulative + new
            yield StepView(
                bag_index=bag_index, bag_name=bag_name,
                step_in_bag=step_in_bag, step_global=step_global, total_steps=total,
                cumulative=list(cumulative), new=new, parts=_parts(new),
            )
