# SnapBlock manual generator

Standalone, pure-Python tool that turns a **build-plan JSON** into a cute nanoblock-style
PDF booklet you can follow to hand-build a model.

It has **no dependency on Blender / bpy** and is **not part of the shipped add-on** — it
lives alongside it and shares only the build-plan file format
(see [`../docs/build_plan.md`](../docs/build_plan.md)).

## Run it

```sh
pip install -r manual/requirements.txt

# One-shot: voxel model (.vox or voxel JSON) -> PDF manual
python -m manual.build manual/samples/mushroom_voxel.json
python -m manual.build model.vox --overrides model.colors.json --plan-out plan.json

# Or run the stages on their own:
python -m manual.planner  manual/samples/mushroom_voxel.json -o plan.json   # voxel -> build plan
python -m manual.generate manual/samples/house.json                          # build plan -> PDF
```

## Pipeline

```
model.vox / voxel.json ─[vox_import]→ voxel model ─[planner]→ build plan ─[generate]→ PDF
```

```
manual/
├── build.py           # one-shot: voxel -> plan -> PDF
├── vox_import.py      # MagicaVoxel .vox (+ voxel JSON) -> voxel model  (stdlib only)
├── planner.py         # voxel model -> build plan: merge + stud/smooth + order + chunk
├── catalogue.py       # rectangular block catalogue (synced w/ snapblock/constants.py)
├── generate.py        # build plan -> PDF (cover, step grid, finished page)
├── buildplan.py       # load/validate a plan, walk it as per-step views (stdlib only)
├── iso.py             # isometric drawing: blocks, studs, smooth tops, hover + drop-lines
├── samples/
│   ├── mushroom_voxel.json   # voxel model: smooth ground + override-studded cap
│   ├── house.json            # hand-authored build plan (all 1x1)
│   └── blob.vox              # tiny .vox fixture for the importer
└── references/        # example manuals you dropped in, for designing the look
```

## The deterministic algorithm

`planner.py` is fully deterministic (same input → byte-identical plan):

1. **Stud vs smooth** per exposed-top cell: a large flat exposed region (≥ `SMOOTH_MIN_REGION`)
   reads as **smooth**; small/bumpy exposed tops stay **studded**; a per-material override
   (`overrides` in the voxel model, or a `.vox` sidecar) forces either. Covered tops never
   get studs.
2. **Merge** cells into rectangles (capped greedy, per layer, per material+finish), with
   **staggered seams** between layers (scan direction alternates by layer parity).
3. **Order** bottom-up so nothing is placed in mid-air.
4. **Chunk** into steps (`STEP_MAX` blocks, within a layer) and bags (`BAG_LAYERS` per bag).

## Status

**Working end to end:** `.vox`/voxel JSON → deterministic plan (varied merged blocks,
auto stud/smooth + overrides, staggered seams, steps/bags) → nanoblock-style PDF (cover,
step grid with hover + drop-lines + per-step parts list, finished page).

## Known issues / notes for next time

1. **Studs must be drawn per-STEP from current exposure, not from the final model.**
   `planner.py` precomputes each block's `studs` from the *finished* build (cells with
   nothing above them at the end). So a cell that gets covered in a later step shows **no
   stud even in the earlier steps where it's still exposed** — the build reads wrong (you
   place a piece onto an apparently studless spot). Physically the stud is always there
   (it's what holds the piece above); a manual just stops *drawing* it once hidden.
   Fix: compute stud visibility in the renderer per step from the cumulative occupancy —
   a studded block shows a stud on cell `(x,y,z)` iff `(x,y,z+1)` isn't filled *yet at
   that step*. Smooth tiles still never get studs. Probably move stud computation out of
   the plan into `generate.py`/`iso.py`; the plan would just carry each block's `finish`.

2. **No support / connectivity check — builds can have loose or floating pieces.**
   `planner.py` orders bottom-up but never checks that each piece rests on / connects to
   the rest of the build. `mushroom_voxel.json` is a bad example: the 4×4 cap sits on a
   2×2 stem (outer ring overhangs into air) and the flat ground tiles are only "held" by
   a baseplate we don't model (loose). Need some of: a self-supporting sample, an assumed
   baseplate, and/or a planner check that flags/forbids unsupported cells (every non-floor
   cell has a filled cell below it, or the whole model is connected).

Cosmetic polish also still open: sub-assembly callouts, a header band (set number /
difficulty), tighter diagram centering, and true brick-bond (current stagger is a
per-layer scan-direction heuristic).

The build-plan JSON is the contract shared with the in-Blender toy, which will later read
the same file to drive the hand-build (current step, optional ghost hint, honor-system
checkoff, one collection per bag). Neither side imports the other — they agree only on the
format.
