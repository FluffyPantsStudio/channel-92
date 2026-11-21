# Characters have a sheet: every view, tall, filled, on a plain backdrop

A character is anyone the pictures must keep the same: the star (`film.json` `star`) and every entry of
`characters`. Each one has a **sheet** modelled on a studio reference board (Claudia's at claudia.gallery is the
model): not one portrait, and never a small figure standing in a wide frame or a picture with a place behind it.

Why: a model that has seen one picture of a face draws every angle from it (a back view comes out with the front's
face on it); a figure that is a thin strip in a wide picture teaches it almost nothing of the face (the first masters of
one film had faces a few dozen pixels tall); and a picture with a street behind it carries the street into every shot.

## The views

Seven separate pictures per character (`data/rules/character-views.txt`; a film's own `rules/` folder can replace the
list):

| View | Is |
|---|---|
| `front`, `three_quarter`, `profile`, `back` | head and shoulders, cut at the chest, from the front, turned about 45 degrees, from the side, from behind. Tall portrait, three to four, the head filling it. |
| `body_front`, `body_three_quarter`, `body_back` | the whole figure from head to feet, the same outfit, filling the height of a tall portrait picture, two to three. |

Optionally `expressions`: a list of up to five head pictures (calm, a smile in the eyes, sad, angry, a singing mouth)
for the characters who sing or act close up. They are shown on the board, not linted.

```json
"star": {"name": "Frankie", "who": "one sentence from canon",
         "views": {"front": "refs/frankie-front.png", "three_quarter": "refs/frankie-three-quarter.png",
                   "profile": "refs/frankie-profile.png", "back": "refs/frankie-back.png",
                   "body_front": "refs/frankie-body-front.png", "body_three_quarter": "refs/frankie-body-three-quarter.png",
                   "body_back": "refs/frankie-body-back.png"},
         "expressions": ["refs/frankie-calm.png", "refs/frankie-sad.png"]},
"characters": {"Ada": {"who": "one sentence from canon", "views": {"front": "...", "...": "..."}}},
"style": "1990s cel-shaded anime"
```

`who` is the one sentence that says who the character is, from canon and approved by the person. `style` (optional) is
said once in every sheet prompt.

## What the kit does about it

| Where | What |
|---|---|
| `refs FILM` | Writes `plan/refs/STEM-VIEW.prompt.txt` for every view not yet named and prints, for each, the size and the picture it makes (`1152x1536` for a head view, `1024x1536` for a full-length one). A prompt that exists is kept unless `--force`. Each prompt asks for a tall portrait the figure fills, on a plain neutral studio backdrop with no environment, one figure only. Make the front view first; make the others from it with the still graph's image input, so they are the same person; draw the back views without the front picture as a reference. Save each as a PNG and list it under `views`. |
| `refs FILM --board` | Writes `refs/boards/STEM-board.png` for each complete sheet: a large front portrait and the full-length front down the left, the head views, the optional expression row, and the other full-length views, laid out like a studio reference board. This is the one picture a director reviews on a phone at gate 3; the separate pictures are what the lint measures and the shots use. Needs Pillow. |
| `progress` | Per character: the views the sheet lacks, a view with an environment behind the figure, a view too small, or ok. |
| `lint` CHR1 (blocks) | Every character has all the views, and every named picture is in the film folder. |
| `lint` CHR4 (blocks) | **Size, measured on the picture:** a view is a tall portrait (height at least 1.2 times its width) and the figure covers at least 80 % of its height. A figure standing small in a wide frame fails. |
| `lint` CHR2 (blocks) | **Backdrop, a coarse screen on the picture:** at least 70 % of the band along the top and both sides (12 % of the size) is smooth (no edges or texture), so a flat or softly lit studio backdrop passes (Claudia's real panels do) and a busy place fails. It does not catch a flat-coloured wall or a plain sky: the cold judge and the person at gate 3 look at that, at full size. Save views as 8-bit RGB PNG, not interlaced or indexed, so this can be measured; a measurement is remembered in `cache/plain.json` until the file changes. |
| `lint` CHR3 (blocks) | A shot with `view:` (any of the seven) takes that view in its still's refs. A back view never carries the front view too: its face would be copied onto the back of the head. |
| gate 3 | Shows the review boards, with the first frames. |

A shot names the angle it shows with `view:` in the shot list (one angle for the whole still, so a shot with two
people facing different ways is two stills). A still made without a `view:` takes the front view (the identity
reference, L022) as before; with a `view:` the still takes that view as its identity reference and L013's hero check
steps aside. A character with a sheet can drop its old `identity` picture: while `identity` is set it is still the
front reference L022 asks for, and nothing measures it.

## Making a view: what worked, what did not

From the character masters of the third film (an anime film on cel-style art, a Klein-class image-edit model, ComfyUI).

**Works**
- Tall sizes straight into the model (1152x1536 head views, 1024x1536 full-length): the figure fills the cell.
- The image-edit model keeps the **first reference's framing and pose**. To turn a head, put a **pose plate** first: a
  grey mannequin bust with a bald, faceless egg head. A plate with a face or hair leaks that face into the character
  (a child character got an adult face). Body plates are clothed in a plain grey coverall: never nude, for any
  character, and above all not for a child.
- Turned heads: the pose plate as the **only** reference and the person in words. A face picture as a second reference
  pulls the head back to the front.
- A full figure for a character whose approved picture is a close-up: reference 1 a plain full-figure front plate
  (framing only), reference 2 the face, and the words "take nothing else from reference 1".
- A hero portrait: reference 1 the approved face at about 832x1088, "head and shoulders, the face filling the upper
  half": fine marks (a cheek line, a collar) read at full size.
- CCIP (dghs-imgutils, MIT; a face-similarity model for anime characters) separates characters well (two characters'
  mean difference 0.37 against a threshold of 0.18) and catches grossly off-model tries. It does **not** catch a drifted
  face of the same character (a known-bad try scored the same as good ones). Use it as a first filter, then a cold
  judge at full size. Installing it downgraded numpy to 1.26 and swapped opencv in the environment it was installed
  into: install it where that is safe.

**Does not work**
- A style pass over finished views (an img2img anime model at low strength): it unifies the look but drops garments and
  fine marks, makes profiles childlike, and adds lettering and faces in textures.
- One image-edit model (Qwen-Image-Edit 2511) for character views: poor in our test.
- Image-to-3D on a flat cel portrait: it built a flat card, not a head, so turning it only tilts the card. Not tried on
  a full figure.
- A LoRA training set made of approved front views: one pose learned very well and nothing of the sides or the back.
  A set needs real angle variety first, and the person approves it before any training starts.
- Text-to-image for places adds face posters to the walls: put "poster, portrait, face, character art" in the
  negative prompt for scenery.

Prompts that name an environment get one, and so do reference pictures with a place in them. So the prompt never
describes a place, and the picture is checked, not trusted. Never retouch a picture's edge to pass a check: the checks
exist to protect the shots made from it. A cold judge opens every view at full size and answers: is the figure alone on
a plain backdrop, are the marks right on this view, is it the same person as the front.
