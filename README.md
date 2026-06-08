# SnapBlock

SnapBlock is a Blender add-on for building things out of snap-together blocks. You pick
a block from the sidebar, it drops onto a grid, and you snap more next to it and color
them in. Every block you place is just a regular Blender object, with a regular
material, in a regular collection. Nothing is faked or hidden behind the scenes.

It's a toy I built for myself. I like building with blocks in Blender — it's tedious but
weirdly therapeutic — and this takes the tedium out of it. Because everything it makes
is real Blender data, I can keep editing a build by hand whenever I want, and turning
the add-on off leaves the scene perfectly intact.

## What works right now

- Placing blocks. Pick one from the sidebar, it lands on the grid, snapped and selected.
- Coloring. Click a swatch, it applies a material (`SnapBlock_Red`, and so on) and reuses
  it across blocks of the same color.
- Moving. The Move panel buttons shift the selection one whole grid cell at a time so
  things stay lined up.
- Rotating and deleting. Turn the selection 90° in place (staying on the grid), or remove
  it (Ctrl+Z brings it back).

It all runs in Blender. Still on the list: rebuild the block library at the current grid
scale and double-check block orientation.

## Notes on the code

A few things I'd point at:

- Everything is real Blender data. No custom data blocks, no hidden state. The scene
  survives without the add-on, which is the entire point.
- Positions are integers. A block's position is stored as a whole grid cell and only
  turned into world coordinates when it's placed. Origins sit at the block's corner, not
  its center. Otherwise odd-width and even-width blocks land on slightly different grids
  and stop lining up.
- One operator per action. Add, color, nudge, rotate, and delete are separate operators
  instead of one big one that branches.
- No tracebacks reach the user. A missing file or an empty selection gives a plain
  message.
- bpy shifts between versions. One material input got renamed in Blender 4.x, so the code
  checks for it instead of assuming it's there.

Written in Python against Blender's API (`bpy`), for Blender 4.2+.

## The dev bridge

`bpy` only exists inside Blender, so testing add-on code usually means pasting a script
into Blender's scripting tab, running it, and copying the output back. I got tired of
that and wrote a bridge.

It's a socket server running inside Blender. Send it Python, get the result back. The
catch is `bpy` isn't thread-safe, so it can't run on the socket thread. Requests go on a
queue and run on Blender's main thread through a timer, then the result gets passed back.
It's also wired up as an MCP server so an AI assistant can drive it while I work. Dev
tool only, not shipped. See `dev/README.md`.

## What's next

Placing, coloring, moving, rotating, and deleting are all written and running. Left to
do:

- Rebuild the block library at the current scale (one grid cell = one Blender unit).
- Check block orientation.

Not packaged for download — this is a personal project, so there's no install step.

Things left out on purpose (for now):

- Importing your own blocks
- Textures
- Animation
- Export to other block formats

## Naming

They're "blocks" or "snap blocks," not "LEGO" or "bricks." The shapes are custom anyway,
not real LEGO proportions — so the name just keeps things consistent.
