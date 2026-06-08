"""
One-shot: voxel model -> deterministic build plan -> PDF manual.

Usage:
    python -m manual.build manual/samples/bonsai_voxel.json
    python -m manual.build model.vox -o model_manual.pdf --overrides model.colors.json
    python -m manual.build model.vox --plan-out model_plan.json   # also keep the plan

Chains vox_import -> planner -> generate. Each of those is runnable on its own too.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import buildplan, generate, planner, vox_import


def main(argv=None):
    parser = argparse.ArgumentParser(description="Voxel model -> nanoblock-style PDF manual.")
    parser.add_argument("voxel", help="voxel model (.vox or voxel JSON)")
    parser.add_argument("-o", "--out", help="output PDF (default: <voxel>_manual.pdf)")
    parser.add_argument("--overrides", help="optional sidecar JSON of colour renames / finishes")
    parser.add_argument("--plan-out", help="also write the intermediate build-plan JSON here")
    args = parser.parse_args(argv)

    generate._require_reportlab()

    voxel = vox_import.load_voxel(args.voxel, args.overrides)
    build_plan = planner.plan(voxel)

    if args.plan_out:
        Path(args.plan_out).write_text(json.dumps(build_plan, indent=2), encoding="utf-8")

    plan_obj = buildplan.plan_from_dict(build_plan)
    out = Path(args.out) if args.out else Path(args.voxel).with_name(Path(args.voxel).stem + "_manual.pdf")
    steps = generate.render(plan_obj, out)
    print(f"Wrote {out}  ({steps} steps, '{plan_obj.name}')")


if __name__ == "__main__":
    main()
