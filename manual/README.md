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
   get studs. The **foundation (lowest) layer never auto-smooths** — a studless base cell
   has nothing above *or* below to anchor it, so it would merge into loose pieces; keeping
   the base studded makes it a solid, connected foundation (an override can still force it).
2. **Merge** cells into rectangles (greedy, per layer, per material+finish), with
   **staggered seams** between layers (scan direction alternates by layer parity). Piece
   size is a **ratio of the region**, not a flat cap: a piece spans at most
   `MERGE_PIECE_RATIO` of a region's long side (floored at `MERGE_MIN_CAP`, ceilinged at
   the largest catalogue block), so a region gets roughly a constant *number* of pieces —
   small details stay small, a wide base earns big slabs instead of being banned outright.
3. **Order** bottom-up so nothing is placed in mid-air.
4. **Check** the build is sound: every piece is supported (something directly below, or it's
   on the `z==0` baseplate) and the whole thing is connected by stud coupling (no loose
   pieces — see the support/connectivity note below). If the first merge leaves a piece
   floating or loose, a **connectivity-repair pass** re-merges just the affected groups with
   the cap lifted to the catalogue ceiling (fewest, biggest pieces), so e.g. a wide base
   consolidates into one slab the thin top can couple onto. Shapes only an L/T block could
   save still fall through — the error message says so.
5. **Chunk** into steps (`STEP_MAX` blocks, within a layer) and bags (`BAG_LAYERS` per bag).

## Status

**Working end to end:** `.vox`/voxel JSON → deterministic plan (varied merged blocks,
auto stud/smooth + overrides, staggered seams, steps/bags) → nanoblock-style PDF (cover,
step grid with hover + drop-lines + per-step parts list, finished page).

## Fixed

1. **Per-step studs (was: studs drawn from the final model).** Stud visibility is now a
   render-time function of `finish` + cumulative occupancy, not stored in the plan: a
   studded block shows a stud on a cell while nothing is stacked on it *yet at that step*,
   so it appears while exposed and vanishes once covered (`iso.visible_studs` /
   `buildplan.occupancy`). The plan no longer carries a `studs` array; a legacy one is
   ignored.

2. **Support + connectivity checks.** `planner.py` refuses a build that isn't soundly
   hand-buildable, listing the offending pieces; pass `--allow-floating` to downgrade to a
   warning and build anyway.
   - **Support:** every block above the baseplate (`z>0`) must have a filled cell directly
     below at least one footprint cell (`z==0` rests on the assumed baseplate). One
     supporting cell is enough, so overhang/cantilever is fine — the *block* just can't
     float. (`samples/floating_test.json` trips this.)
   - **Connectivity:** the whole model must hold together as one piece under stud coupling —
     each block joins the rest by sitting directly on or directly under another block
     (transitively: a chain of couplings back to the main assembly is enough). Same-layer
     neighbours don't couple and there's no assumed baseplate, so the test is "lift the
     model and it stays in one piece." This catches loose islands a wide flat base used to
     fragment into — though the foundation rule above now prevents the common case
     (`mushroom_voxel.json`'s 4×4 ground stays studded, merges into two connected 4×2
     bricks, and passes).

## Known issues / notes for next time

Cosmetic polish done (`generate.py` / `iso.py`): a warm but restrained SnapBlock identity
— soft warm-white paper, the lightly-rounded **Mulish** typeface (bundled in `assets/`,
falls back to Helvetica), one muted clay-rose accent (header band, step badges, badge),
an editorial tracked "BUILD MANUAL" / "BAG N" treatment, a tinted parts strip, quiet tag
pills, sticker cards with soft shadows, a "Finished" badge, and soft ground shadows under
the hero diagrams so the model sits in space. The whole palette is a handful of constants
at the top of `generate.py` (`ACCENT`, `PAPER`, `INK`, …) — easy to re-tune.

Still open: sub-assembly callouts, a difficulty rating in the band, and true brick-bond
(current stagger is a per-layer scan-direction heuristic).

The build-plan JSON is the contract shared with the in-Blender toy, which will later read
the same file to drive the hand-build (current step, optional ghost hint, honor-system
checkoff, one collection per bag). Neither side imports the other — they agree only on the
format.
