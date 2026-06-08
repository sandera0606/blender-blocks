"""
Load and walk a build-plan (see ../docs/build_plan.md).

Pure standard library — no Blender, no drawing deps. This module is the shared
understanding of the format: load it, validate it lightly, and iterate it as a
sequence of per-step "views" the renderer can draw one page from.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Block:
    x: int
    y: int
    z: int
    type: str
    material: str

    @property
    def cell(self) -> tuple[int, int, int]:
        return (self.x, self.y, self.z)


@dataclass
class Part:
    """A line in a step's parts list: how many of one (material, type)."""
    count: int
    material: str
    type: str


@dataclass
class StepView:
    """Everything the renderer needs to draw one page."""
    bag_index: int
    bag_name: str
    step_in_bag: int          # 1-based within the bag
    step_global: int          # 1-based across the whole plan
    total_steps: int
    cumulative: list[Block]   # all blocks placed up to AND including this step
    new: list[Block]          # the blocks added in this step (highlight these)
    parts: list[Part]         # derived from `new`


@dataclass
class Plan:
    name: str
    grid_u: float
    grid_h: float
    palette: dict[str, tuple[float, float, float]]
    bags: list[dict] = field(default_factory=list)


class PlanError(ValueError):
    """A build plan that doesn't conform to the format."""


def load_plan(path: str | Path) -> Plan:
    """Read and lightly validate a build-plan JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    version = data.get("version")
    if version != 1:
        raise PlanError(f"unsupported build-plan version: {version!r} (this tool reads 1)")

    palette_raw = data.get("palette") or {}
    palette = {name: tuple(rgb) for name, rgb in palette_raw.items()}

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
                mat = b.get("material")
                if mat not in palette:
                    raise PlanError(
                        f"block at cell {b.get('cell')} uses material {mat!r}, "
                        f"which isn't in the palette"
                    )
    return plan


def _parts(blocks: list[Block]) -> list[Part]:
    """Count blocks by (material, type) for a step's parts list."""
    counts = Counter((b.material, b.type) for b in blocks)
    # Stable, readable order: by material then type.
    return [Part(count=n, material=m, type=t)
            for (m, t), n in sorted(counts.items())]


def iter_steps(plan: Plan):
    """Yield a StepView per step, accumulating the build as we go.

    The plan stores only per-step deltas (`add`); the manual wants the cumulative
    picture with the new blocks highlighted, so we build that here once.
    """
    total = sum(len(bag.get("steps", [])) for bag in plan.bags)

    cumulative: list[Block] = []
    step_global = 0
    for bag_index, bag in enumerate(plan.bags):
        bag_name = bag.get("name", f"Bag {bag_index + 1}")
        for step_in_bag, step in enumerate(bag.get("steps", []), start=1):
            step_global += 1
            new = [
                Block(x=c[0], y=c[1], z=c[2], type=b.get("type", "1x1"), material=b["material"])
                for b in step.get("add", [])
                for c in [b["cell"]]
            ]
            cumulative = cumulative + new
            yield StepView(
                bag_index=bag_index,
                bag_name=bag_name,
                step_in_bag=step_in_bag,
                step_global=step_global,
                total_steps=total,
                cumulative=list(cumulative),
                new=new,
                parts=_parts(new),
            )
