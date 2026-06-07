# SnapBlock

A Blender 4.2+ add-on that gives adult beginners a snap-block toy to play with
inside a real Blender scene. You drop pre-made blocks onto a grid, snap them
together, and color them. Behind the scenes you're left with normal Blender
objects, materials, and collections.

The point isn't to build a separate app inside Blender. It's trainer wheels for
Blender itself. Every action leaves behind a real, editable scene, and a
"show me what's really happening" mode explains the Blender concept behind each
click as you go. Uninstall the add-on and your scene still works.

## Who it's for

People who've heard Blender is powerful, opened it once, and bounced off the
learning curve. The goal is making something fun in about 90 seconds, not
sitting through a four-hour donut tutorial before placing your first cube.

## How it works

- Blocks live on a grid where one cell is 2.0 Blender units. Positions are stored
  as integer grid coordinates and only converted to world space when a block is
  placed, so things always line up.
- You pick a block from the side panel and it appears at the 3D cursor, snapped
  to the grid and ready to nudge.
- Colors are preset swatches. Each one maps to a plain Principled BSDF material
  named `SnapBlock_<color>`, nothing exotic.
- Placed blocks are named `Block_<type>.<counter>` and grouped in a collection
  called `SnapBlock Build`, because the Outliner is part of learning Blender, not
  something to hide.

A note on naming: these are "blocks" or "snap blocks," never "LEGO" or "bricks."
That's a trademark thing, not a style preference.

## Installing and using the add-on

Heads up: v0.1 isn't packaged yet, so there's no zip to download today (see
Project status below). When it ships, it installs the normal Blender way:

1. Get `snapblock.zip` (a release download, or zip up the `snapblock/` folder
   yourself). Keep it zipped — don't unzip it first.
2. In Blender: Edit > Preferences > Add-ons > Install from Disk, then pick the zip.
3. Tick the checkbox next to "SnapBlock" to enable it.
4. In the 3D viewport, press `N` to open the side panel and click the **SnapBlock**
   tab.

Then, to actually build something:

1. Click a block in the panel. It drops in at the 3D cursor, snapped to the grid.
   Press `G` to slide it around (snapping stays on) or `R` to rotate.
2. Select one or more blocks and click a color swatch to paint them.
3. Flip on **"Show me what's really happening"** to see the real Blender action
   behind each click, plus a plain-English glossary.

Everything you make is ordinary Blender data. Look in the Outliner (top right) and
you'll see your blocks as real objects in a collection called `SnapBlock Build`.

## Project status

Early. The repo currently holds the design and source assets, not a finished
add-on. Here's what's here:

- `SNAPBLOCK_BRIEF.md` — the full design brief and the source of truth for scope
  and rationale. Start here if you want the details.
- `CLAUDE.md` — working rules for anyone (including Claude Code) touching the repo.
- `source_blocks/all_blocks.blend` — the master library of ~22 hand-modeled
  blocks. This file is read-only and never edited in place.
- `legacy__init__.py` — a partial earlier attempt. Useful scaffolding, not a
  working add-on.
- `dev/` — developer tooling (see below). Not shipped with the add-on.

The `snapblock/` add-on folder described in the brief doesn't exist yet.

## dev/ — Blender bridge for development

Working on a Blender add-on means running `bpy`, which only exists inside Blender.
The `dev/` folder has a small bridge that lets Claude Code run code in a live
Blender session over a localhost socket, instead of pasting scripts into the
Scripting tab by hand. It's a development convenience and has nothing to do with
the shipped add-on. Setup and details are in `dev/README.md`.

## Building it

The build order, the v0.1 milestone, and what's deliberately left out are all in
`SNAPBLOCK_BRIEF.md`. The short version of "done" for v0.1: a new user can build
a tiny house in about 90 seconds, end up with real Blender objects, and color
them along the way.
