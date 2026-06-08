# SnapBlock manual generator

Standalone, pure-Python tool that turns a **build-plan JSON** into a cute nanoblock-style
PDF booklet you can follow to hand-build a model.

It has **no dependency on Blender / bpy** and is **not part of the shipped add-on** — it
lives alongside it and shares only the build-plan file format
(see [`../docs/build_plan.md`](../docs/build_plan.md)).

## Run it

```sh
pip install -r manual/requirements.txt
python -m manual.generate manual/samples/house.json
# -> writes manual/samples/house_manual.pdf
```

(`python manual/generate.py manual/samples/house.json` works too.)

## Layout

```
manual/
├── generate.py        # CLI: build-plan JSON -> PDF (one page per step)
├── buildplan.py       # load/validate a plan, walk it as per-step views (stdlib only)
├── iso.py             # isometric cube drawing (first pass — to be tuned)
├── samples/
│   └── house.json     # hand-authored plan to iterate against
└── references/        # example manuals you drop in, for designing the look
```

## Status

**Scaffold / first pass.** The pipeline runs end-to-end (JSON in, PDF out), but the
*look* — cube style, shading, studs, page design, a cover page — is deliberately crude
and meant to be redesigned against real reference booklets in `references/`. Add some
examples there and we'll make it adorable.

The build-plan JSON is the contract shared with the in-Blender toy, which will later read
the same file to drive the hand-build (current step, optional ghost hint, honor-system
checkoff, one collection per bag). Neither side imports the other — they agree only on the
format.
