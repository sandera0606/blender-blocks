# SnapBlock

SnapBlock is a Blender add-on that lets beginners build things out of snap-together blocks. You
pick a block from the sidebar, it drops onto a grid, and you snap more next to it and color them
in. Every block you place is just a regular Blender object, with a regular material, in a regular
collection. Nothing is faked or hidden behind the scenes.

That's the whole idea. Get someone making something in Blender in a couple of minutes without
making them learn the interface first, but have everything they make be real Blender data they
can keep using later. Turn the add-on off and the scene still works.

## Reveal mode

There's a toggle: "Show me what's really happening." Turn it on and the add-on starts narrating
itself. Hover a button and the tooltip tells you which Blender operation it runs. A glossary
panel explains the words beginners keep hitting (Object, Mesh, Material, Collection, and so on).
After each action, a panel shows what just happened. The point is that someone ends up actually
knowing what an Object or a Collection is, not just that a button worked.

## What works right now

- Placing blocks. Pick one from the sidebar, it lands on the grid, snapped and selected.
- Coloring. Click a swatch, it applies a material (`SnapBlock_Red`, and so on) and reuses it
  across blocks of the same color.
- Moving. Buttons or arrow keys shift a block one whole grid cell at a time so things stay lined
  up.
- Reveal mode, above.

It all runs in Blender. Before I call v0.1 done I still need to rebuild the block library at the
new grid scale and time the "build a small house in 90 seconds" test.

## Notes on the code

A few things I'd point at:

- Everything is real Blender data. No custom data blocks, no hidden state. The scene survives
  without the add-on, which is the entire point.
- Positions are integers. A block's position is stored as a whole grid cell and only turned into
  world coordinates when it's placed. Origins sit at the block's corner, not its center.
  Otherwise odd-width and even-width blocks land on slightly different grids and stop lining up.
- One operator per action. Add, color, and nudge are separate operators instead of one big one
  that branches.
- No tracebacks reach the user. A missing file or an empty selection gives a plain message.
- bpy shifts between versions. One material input got renamed in Blender 4.x, so the code checks
  for it instead of assuming it's there.

Written in Python against Blender's API (`bpy`), for Blender 4.2+.

## The dev bridge

`bpy` only exists inside Blender, so testing add-on code usually means pasting a script into
Blender's scripting tab, running it, and copying the output back. I got tired of that and wrote
a bridge.

It's a socket server running inside Blender. Send it Python, get the result back. The catch is
`bpy` isn't thread-safe, so it can't run on the socket thread. Requests go on a queue and run on
Blender's main thread through a timer, then the result gets passed back. It's also wired up as an
MCP server so an AI assistant can drive it while I work. Dev tool only, not shipped. See
`dev/README.md`.

## Status and what's next

Placing, coloring, moving, and reveal mode are all written and running. Left for v0.1:

- Rebuild the block library at the current scale (one grid cell = one Blender unit).
- Run the 90-second house test end to end.
- Check block orientation and the reveal panels.

Not packaged for download yet, so there's no install step for now.

Things left out of the first version on purpose:

- Importing your own blocks
- Textures
- Animation
- Export to other block formats

## Naming

They're "blocks" or "snap blocks," not "LEGO" or "bricks." It's a trademark thing. The shapes
are custom anyway, not real LEGO proportions.
