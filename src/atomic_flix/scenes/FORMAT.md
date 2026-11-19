# Scene descriptions (`atomic-flix/scene@1`)

A scene is one JSON file that says which building blocks stand where, how the set is lit, what the sky is, how the
viewpoint moves and what to capture. `python -m atomic_flix.scenes check SCENE.json` validates it without Blender;
`plan` prints the flat op list Blender will execute; `capture` builds and renders it; `controls` turns the render into
control clips for a video model.

Units are metres with z up, angles are degrees, frames count from 1. Unknown keys are errors, and every error names
the field (`pieces[2].settings.height: 3.0 is below 5`).

## Two examples

`scenes/pieces/examples/street.json` rebuilds the filing-cabinet street of our first film (the port of
`lab/blender/street.py`): road, two rows of cabinet towers each side, open drawers on the near walls, glass eyes on
stalks, the dusk sky, a key, fill and top light, and the 145-frame push.

```json
{
 "format": "atomic-flix/scene@1", "name": "cabinet-street", "seed": 11,
 "size": {"w": 1920, "h": 1056, "fps": 24, "frames": 145},
 "world": {"sky": {"image": "gen:dusk", "spin": 90, "brightness": 1.0}, "mist": {"start": 5, "depth": 400}},
 "lamps": [
  {"kind": "sun", "name": "key", "color": [1.0, 0.8, 0.745], "power": 5.0, "pitch": -24, "yaw": 196, "soft": 3},
  {"kind": "sun", "name": "fill", "color": [0.94, 0.8, 0.88], "power": 1.0, "pitch": -35, "yaw": 70, "soft": 30},
  {"kind": "sun", "name": "top", "color": [0.59, 0.78, 0.84], "power": 0.25, "pitch": -80, "yaw": -90, "soft": 30}],
 "pieces": [
  {"use": "road", "settings": {"extent": 600, "width": 26}},
  {"use": "tower-row", "id": "front", "at": [0, 25, 0], "twin_across": "redraw"},
  {"use": "tower-row", "id": "back", "at": [0, 43, 0], "twin_across": "redraw",
   "settings": {"start": [9, 15], "width": [13, 20], "height": [35, 65], "gap": [7, 28], "depth": 14}},
  {"use": "drawers", "at": [0, 19, 0], "twin_across": "redraw"},
  {"use": "eye-on-stalk", "id": "eyes", "settings": {"height": [9, 15]},
   "strew": {"along": "x", "from": 18, "to": 520, "step": 33, "nudge": 3, "across": [14.5, 16.5], "flip": "alternate"}},
  {"use": "eye-on-stalk", "id": "eye-near-left", "at": [13, 15, 0], "settings": {"height": 10}},
  {"use": "eye-on-stalk", "id": "eye-near-right", "at": [29, -15, 0], "settings": {"height": 12}}],
 "viewpoint": {"lens": 32, "film_mm": 36, "far": 2000,
  "path": {"move": "push", "from": [0, 0, 1.4], "to": [17, 0, 1.4], "pitch": 7, "yaw": 10.7, "ease": "eased35"}},
 "capture": {"renderer": "raster", "spp": 64, "view": "Standard", "masks": ["eye-on-stalk"]}
}
```

`scenes/pieces/examples/picnic.json` is a day scene: a lawn with a picnic blanket, far ground to the horizon, a figure
standing in for a singing performer, and a slow orbit around her. Its masks give one matte for the performer and one
for the picnic set, and its rig gives the pose guide.

## Top level

| Key | Required | Meaning |
|---|---|---|
| `format` | yes | Always `"atomic-flix/scene@1"`. |
| `name` | yes | The scene's name. |
| `seed` | no (1) | One seed for every draw. Each block instance draws from its own stream (seed, instance id, purpose), so adding or removing a block never changes another block's values. |
| `size` | yes | `w`, `h` (pixels), `fps` (24), `frames` (1). |
| `world` | no | `sky` and `mist`, below. |
| `lamps` | no | A list of lights, below. |
| `pieces` | no | A list of block entries, below. |
| `surfaces` | no | Extra materials by name, added to (or replacing) the library's `scenes/pieces/surfaces.json`. |
| `viewpoint` | yes | Lens and path, below. |
| `capture` | no | Renderer, samples per pixel, layers and masks, below. |

## world

- `sky`: either `{"image": PATH or "gen:<name>", "spin": DEG, "brightness": 1}` (an equirectangular image, turned
  about z) or `{"color": [r, g, b], "brightness": 1}` (linear). `gen:` names a generated texture (`dusk`, `day`, see
  textures.py); a path is relative to the scene file.
- `mist`: `{"start": 5, "depth": 400}` in metres, for the mist pass.

## lamps

`{"kind": "sun" | "point" | "area", "name", "color": [r, g, b], "power"}`. A sun or area light points by `pitch`
(negative is down) and `yaw`, mapped as street.py maps the Unreal light rotation (Blender euler `(90 + pitch, 0,
yaw + 90)`); a sun has `soft` (its angle in degrees). Point and area lamps have `pos` and `radius`; an area light
also has `size`. Power is Blender's: irradiance for a sun, watts otherwise. Blocks can bring their own lights (the
room's sconce).

## pieces

| Key | Meaning |
|---|---|
| `use` | The block's name in the library (`scenes/pieces/<name>/` in the package). |
| `id` | Optional name for this entry, used for masks and in object names; default the block's name, numbered from the second unnamed one (`box`, `box-2`). No `/` or `~`. |
| `at` | Where its origin goes, `[x, y, z]`. |
| `turn` | Degrees about z, counter-clockwise from above. |
| `twin_across` | `true` adds a mirror image across y = 0 (same draws); `"redraw"` adds a mirrored twin that draws its own values (each side of a street different, as street.py did). The twin's id ends in `~m`. |
| `settings` | The block's own params (see each `block.json`). A number param given as `[a, b]` is drawn once for this instance. A `span` param stays a range and the builder draws from it per part (each tower's height). |
| `strew` | Many copies along a line: `{"along": "x" or "y", "from", "to", "step", "nudge", "across": number or [a, b], "flip": "none" or "alternate"}`. Copy k sits at from + k * step (to is not reached) plus a nudge draw, offset sideways by `across` (drawn per copy), with every even copy flipped to the other side when `flip` is `"alternate"`. Copies are named `<id>/<k>`. |

## viewpoint

`{"lens": 32, "film_mm": 36, "near": 0.1, "far": 1000, "path": {...}}`. The film back (`film_mm`) is fitted to the width.

`path` is either a `move` or keys.

- `still` and `handheld`: `pos`, `yaw`, `pitch`, `roll`. Handheld adds a seeded slow wobble (`amp_cm` 1.5, `amp_deg`
  0.4, `hz` 0.35).
- `push`, `pull`, `truck`, `crane`: `from` and either `to` or `distance` (forward, back, to the camera's right, up),
  with `yaw`, `pitch`, `roll` and `ease`.
- `orbit`: `center`, `radius`, `height`, `start` and `end` (degrees around z), `ease`; looks at the centre (or `look`).
- Any preset may carry `"shake": {"amp_cm", "amp_deg", "hz"}`.
- `keys`: `[{"f": 1, "pos": [x, y, z], "look": [x, y, z] or "yaw"/"pitch"/"roll", "lens": 32, "ease": "eased"}]`,
  frames rising; the ease on a key shapes the segment that ends there. Before the first and after the last key the
  camera holds.

Eases: `even`, `eased` (smoothstep), `eased35` (street.py's push: smoothstep * 0.35 + t * 0.65), `in`, `out`.
A heading of 0 looks down +x and 90 down +y; pitch is up.

## capture

| Key | Default | Meaning |
|---|---|---|
| `renderer` | `raster` | `raster` or `pathtrace`. |
| `spp` | 64 | Eevee TAA samples or Cycles samples. |
| `device` | `gpu` | Cycles device; `gpu` tries OptiX then CUDA, else CPU. |
| `view` | `Standard` | Colour view. Standard, so a video model sees what we see. |
| `layers` | all | `shaded`, `depth`, `facing`, `mist`, `mask`. |
| `masks` | none | Block ids or block names; each gets its own matte. |
| `frames` | all | `[a, b]` to render part of the shot. |
| `step` | 1 | Every n-th frame (`--quick` uses 4). |
| `depth_range` | `[0.5, far]` | Near and far metres for the 16-bit depth PNG. |

## What a capture writes (OUT/)

| File | Content |
|---|---|
| `plan.json` | The compiled ops (reset, settings, world, surface, prim, rig, light, viewpoint with one key per frame, layers, renderer, capture). |
| `scene.lock.json` | Every instance with its resolved settings, the viewpoint and the capture settings. |
| `viewpoint.json` | One record per frame: `f`, `pos`, `quat_wxyz` (Blender camera rotation), `lens_mm`, `fov_x_deg`, `K`, `to_view` (OpenCV: x right, y down, z forward). |
| `shaded/0001.png` | 8-bit sRGB, Standard view. |
| `depth/0001.exr` | Depth in metres (float32, channel Z); the sky is `far`. |
| `depth/0001.png` | 16-bit inverse depth over `depth_range`: near white, far and sky black. |
| `facing/0001.png` | Camera-space normals, x right, y up, z toward the viewer, mapped to 0..255. |
| `mist/0001.png` | 8-bit mist. |
| `mask/<name>/0001.png` | 0 or 255 per pixel for each name in `masks`. |
| `capture.json` | Renderer, Blender version, seconds per frame (render and pass writing) and their means. |
| `tex/` | The generated textures the plan used. |

## Blocks library (`scenes/pieces/`, shipped as package data)

Each block is a folder with `block.json` and `build.py`.

A scene's `use` is a block name, never a path: lower-case letters, digits and hyphens, starting with a letter or
digit (`^[a-z0-9][a-z0-9-]*$`), naming a folder directly inside the library. Anything else is refused before a
builder is loaded, as is a folder or `build.py` that resolves outside the library (a link pointing elsewhere).
Scenes build from the pieces packaged with the kit. Your own block folder is used only when you name it on the
command line with `--blocks DIR` (check, plan, capture, blend); its `build.py` files run as Python with your
rights, so name only a folder you trust. No scene field or environment variable adds a block folder.

```json
{
 "name": "box", "version": 1,
 "summary": "One box standing on the ground (or lifted), for stand-ins, backdrops and tests.",
 "settings": {
  "size": {"type": "vec3", "fallback": [1, 1, 1], "min": 0.001},
  "lift": {"type": "float", "fallback": 0.0},
  "yaw": {"type": "float", "fallback": 0.0},
  "surface": {"type": "surface", "fallback": "drawer"}
 },
 "ground_box": [-0.5, -0.5, 0.5, 0.5], "tags": ["prop", "test"], "surfaces": ["drawer"],
 "provenance": "hand-written", "rights": "ours"
}
```

Param types: `float`, `int` (a number, or a range drawn once per instance), `span` (a range the builder draws from),
`bool`, `str` (optional `choices`), `vec2`, `vec3`, `surface` (a material name). `min` and `max` bound numbers.

`build.py` holds `def build(ctx, settings)` and makes everything through `ctx`, in the block's own frame:
`ctx.box(pos, size, surface, name, yaw)`, `ctx.tube(pos, radius, height, surface)`, `ctx.ball(pos, radius
or [dx, dy, dz], surface)`, `ctx.limb(a, b, radius, surface)`, `ctx.light(kind, pos, power, color, radius)`,
`ctx.rig(frames)`, `ctx.to_local(world_point)`, `ctx.rng` (the instance's random stream), `ctx.frames`, `ctx.fps`.
Every shape takes `quat` (w, x, y, z) and `keys` (one (pos, quat) per frame) for animation. The context places,
turns and mirrors what the builder makes and tags it with its block for masks.

Blocks today: `box`, `road`, `tower-row`, `drawers`, `eye-on-stalk` (the street), `chest-of-drawers`,
`kitchen-counter`, `lawn-picnic`, `salt-flat`, `room-wall-light`, `figure`.

Surfaces (`scenes/pieces/surfaces.json`): `{"kind": "flat", "srgb" or "color", "gain", "rough", "metal", "specular",
"emit"}` or `{"kind": "image", "image": "gen:<name>" or a path, "scale": [x, y, z], "blend", ...}`. Image materials
are projected in world space from three sides (the cabinet recipe from street.py: 2 drawers across in 3.6 m, 4 down
in 6 m), so boxes of any size show the texture at one scale.

## Controls

`python -m atomic_flix.scenes controls OUT/ --for ltx --size 1152x640` writes `OUT/controls/`: depth, canny, edges and
(with a figure) pose clips, the first and last shaded frames at the guide size, and `controls-<model>.json`. Sizes
must suit the model: LTX-2.3 with the union control needs both sides to be multiples of 128 (it halves the frame and
needs even latents: 1152x640 works, 1280x704 does not); SCAIL-2 and Wan need multiples of 32. A wrong size is an
error.
