# Build-plan format (the contract)

The **build plan** is a single JSON file that fully describes a build as an ordered
sequence of steps. It is the one source of truth shared by two independent programs:

- **the manual generator** (`manual/`, pure Python, no Blender) — reads a plan and renders
  a cute nanoblock-style PDF booklet.
- **the in-Blender toy** (`snapblock/`, bpy) — *(later)* reads the same plan to drive the
  hand-build experience (current step, ghost hint, honor-system checkoff, bag-collections).

Neither program imports the other. They agree only on this file format. That keeps the
bpy / pure-Python split clean: the generator never has to load `bpy`, and the add-on
never has to load the generator's drawing deps.

## Shape

```json
{
  "version": 1,
  "model": { "name": "Tiny House" },
  "grid": { "U": 1.0, "H": 1.0 },
  "palette": {
    "Gray":   [0.30, 0.30, 0.30],
    "Yellow": [0.85, 0.65, 0.05],
    "Red":    [0.70, 0.05, 0.05]
  },
  "bags": [
    {
      "name": "Base",
      "steps": [
        { "add": [
          { "cell": [0, 0, 0], "type": "4x2", "material": "Gray", "finish": "smooth" },
          { "cell": [4, 0, 0], "type": "2x2", "material": "Yellow", "finish": "stud",
            "studs": [[4,0],[5,0],[4,1],[5,1]] }
        ] }
      ]
    }
  ]
}
```

A build plan is normally produced by `manual/planner.py` from a **voxel model**
(`vox_import.py` reads MagicaVoxel `.vox` or a voxel JSON); it can also be hand-authored.
Pipeline: `model.vox → vox_import → voxel model → planner → build plan → generate → PDF`.

## Fields

- `version` — format version. Currently `1`. Bump when the shape changes incompatibly.
- `model.name` — display name, shown on the manual cover/header.
- `grid.U`, `grid.H` — cell size on X/Y and height on Z, in Blender units. Mirrors
  `snapblock/constants.py`. Carried in the plan so the generator stays self-contained.
- `palette` — maps a **material name** to an RGB triple in 0..1. The generator colors
  cubes from this; it does **not** read the add-on's color presets (decoupling). A plan
  is only valid if every block's `material` exists here.
- `bags` — ordered list. Each bag becomes one collection in Blender and one labelled
  section in the manual.
  - `name` — bag label (e.g. "Base", "Walls", "Roof").
  - `steps` — ordered list. Each step is one page of the manual.
    - `add` — the blocks placed **in this step** ("the blocks involved in the step").
      - `cell` — the block's **bottom −X/−Y corner** as integer grid coords `[gx, gy, gz]`
        (matches the repo's origin convention). The block fills `[gx..gx+W) × [gy..gy+D)`.
      - `type` — the **as-placed** footprint `"WxD"` (e.g. `"4x2"`, `"1x3"`). The renderer
        parses W,D from this. The orientation-independent library id is the dims sorted
        (so `"1x4"` is a `"4x1"` block rotated); parts lists group by that canonical id.
      - `material` — a key into `palette`.
      - `finish` — `"stud"` or `"smooth"` (optional; default `"stud"`).
      - `studs` — the footprint cells `[[cx,cy], …]` that show a stud (optional). The
        planner sets exactly the exposed studded cells; if omitted, a `stud` block defaults
        to its whole top and a `smooth` block to none.

## Rules / conventions

- **Order is the build order.** Bags, then steps within a bag, then the `add` list within
  a step, are all in literal document order. There is no separate ordering field.
- **Build bottom-up, supported.** The plan *should* be ordered so that every block, when
  its step runs, already rests on a neighbour below or beside it — you never place into
  mid-air. (Enforcing/generating this is the voxel→plan step's job, not the format's.)
- **A step's diagram shows the cumulative build** up to and including that step, with that
  step's `add` blocks highlighted. The generator accumulates; the plan only stores deltas.
- **A step's parts list is derived**, not stored: count this step's `add` by
  `(catalogue id, material, finish)`.
- **Smooth ⟹ nothing on top.** A studless tile can't anchor a block, so a `smooth`
  block must never have a filled cell directly above any of its cells. Equivalently,
  any cell with something attached on top must belong to a `stud` block. The planner
  guarantees this (smooth is only assigned to exposed tops) and asserts it.

## Not in the format (deliberately)

- No progress/checkoff state — that's honor-system UI state in the toy, not part of the
  plan.
- No camera/render settings — the generator owns how things look.
- No voxel source — a plan is the *output* of voxelization, not the input model.

> Status: v1, first pass. Expect fields to firm up once we design the manual's look
> against real reference booklets (see `manual/references/`).
