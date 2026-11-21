# Action shots are staged in Blender

A video model draws a first frame well and invents movement badly. A fight, a chase, a jump or a crash asks it for
the one thing it does worst: bodies and vehicles moving through space with contact, momentum and a camera that
follows. Left alone it merges limbs, fakes hits and changes the street between frames. So the kit's rule is:

**Any shot whose written action is a fight, chase, jump, crash or fall has its movement built in Blender. The model
dresses the movement; it does not invent it.**

Blender builds the set, the stand-in figures and the camera path. The kit captures it, makes control clips (depth,
Canny, edges, pose), and a control graph makes the take follow one of them. The first frame still comes from the image
model, so the look is ours; the movement comes from Blender, so it is right.

## What the kit does about it

| Where | What |
|---|---|
| shot list | `blender: scenes/N09-chase.json` on a shot names its scene file. `no_blender: <reason>` is the person's written reason this action needs none (a one-second glimpse, the film's own footage). |
| `lint` (ACT1, blocks) | A shot whose beats or goal name a sure action (`data/rules/action.txt`: fight, chase, sprint, punch, runs away, races past...) and has neither line is refused before any GPU time. |
| `lint` (ACT4, warns) | Words that only sometimes mean action (`data/rules/action-maybe.txt`: leaps, crash, kick, falls back, runs down...) ask a person: stage it, or write why not in film.json `reasons` under `ACT4:KEY` (a tear that runs down a cheek is not a chase). A film's own `rules/action.txt` or `rules/action-maybe.txt` replaces a list; agents never edit them to get past the rule. |
| `lint` (ACT2, ACT3, block) | The scene file must be in the film folder, and the plan must agree with the shot list about Blender (`shoot` reads the plan, so run `plan` again after editing the list). |
| `plan` | A Blender shot's task carries `route: "blender"` and `blender: {scene, out, guide}`. `out` is `blender/KEY/`; `guide` is the shot's `guide:` (depth, canny, edges or pose), else depth. A sung shot cannot be staged in Blender (and its `act` clauses are never read as action): cover the action with a cutaway. |
| `progress` | Lists each action shot with no scene, each shot that may be action, and each Blender shot with the first thing it lacks: the scene file, the capture, the control clips for its guide, or a scene edited after its capture. |
| `lint` (ACT5, warns) | The shot's first frame has most of the Blender first frame's lines: 60 % or more of the blockout's edge pixels have a line of the still within a few pixels. An edit model that recomposes (zooms out, recentres, moves a wall) fails it, and the video model would then animate a layout Blender never had. The threshold is a first guess for calibrating on real frames, so it warns; a reason goes in film.json under `ACT5:KEY`. |
| board and report | A Blender shot's card and row say `(Blender)`. |
| `shoot` | Blender shots render on `--action-graph`, a graph that takes the control clip as `$video`, with `blender/KEY/controls/<guide>-*.mp4` as that input. No clip, clips of two models (it does not guess), a scene edited after its clip, or a graph that could not carry the clip is refused by name rather than rendered without the movement. `budget` costs these renders at plate rates and says so: read the total as a floor. |

## Staging one action shot

1. **Write the scene** (format: `src/atomic_flix/scenes/FORMAT.md`): the blocks of the set, a `figure` for each body,
   the lamps, and the camera path (`handheld`, `push`, `orbit`, or keys for a follow). Stand-in figures carry the
   movement: their keys are the fight, the run, the leap. Put the file at `scenes/KEY.json`.
2. **Check and capture it:** `atomic-flix scenes check scenes/KEY.json`, then
   `atomic-flix scenes capture scenes/KEY.json blender/KEY` (`--quick` first, half size, every fourth frame).
3. **Make the control clips** at the size the graph needs:
   `atomic-flix scenes controls blender/KEY --for ltx --size 1152x640` (`scail` and `wan` take multiples of 32).
4. **Make the shot's first frame** from `blender/KEY/controls/first-<model>.png` plus the character's reference with
   the image model, so the character stands where Blender's figure stands. Check it at full size.
5. `lint`, `plan`, `budget`, gate 5, `shoot`. The shot is one generation (L072); the guide is never slowed (L074).

## Which guide

- **depth** (default): scenery, vehicles, anything solid.
- **pose**: a character whose build differs from the stand-in's. Depth would redraw the stand-in's body over the
  character (L083).
- **canny** or **edges**: thin moving parts (legs, wires, swords), which depth does not see (L082).

## What does not go to Blender

Faces and sung lines. A close-up of her singing is made from a still and the vocal, as always. Blender carries the
bodies and the camera in the wide and medium action shots around it, and the cut puts the two together. Limits worth
knowing: SCAIL-2 over Blender plates is tested to 81 frames, so a longer move is cut into shots, not chained (L072);
the stand-in is a figure, not a performance, so give each action beat a clear pose change a guide can show.

## Keeping the scene plain, and the first frame honest

What practitioners of the Blender-then-restyle pipeline agree on (a published 3D-to-AI action short, and community
Blender-to-Wan workflows; mostly vendor and tutorial sources, with no head-to-head comparisons):

- **Block the shot in plain grey.** Beveled boxes, one flat tone per object so elements separate by tone, no textures,
  no characters, no clutter: small detail is what the restyle model misreads. The scene owns geometry, camera, timing and
  cuts; the image model owns the look.
- **The first frame shows every key element.** If the car only enters later, the model invents it. Move the camera in
  Blender, not the prompt.
- **Move like a real object.** Constant speeds, a true parabola for a jump, the camera and the subject keyed on the same
  frames, handheld noise on the camera only.
- **One readable camera idea per shot.**
- **Restyle the first frame with the Blender frame as the only source of layout**, plus fixed style and character
  references. Crop every reference to the film's aspect (a 16:9 reference overrides a 2.39:1 frame): lint AR1 checks the
  still's shape, ACT5 checks its lines against the Blender frame.
- **Look at the overlay before any video is made.** A perspective error in the first frame is animated faithfully.
  Several seeds per first frame, and keep the one that matches.
- **Guides, by what the shot needs:** depth for spatial fidelity, Canny for composition, pose for a character's motion.
