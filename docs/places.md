# Places have a sheet too

A video model holds no persistent picture of a room. A place that is described again in words for every shot drifts:
the walls, the furniture and the light change from cut to cut. A place is a **record** (pictures), not a description.
Each place a film returns to has a small sheet, and every shot there is made from it. (A character has a sheet too:
`docs/characters.md`. Locations are harder to keep than faces.)

## The sheet

In film.json:

```json
"places": {"alley": {"views": {"wide": "refs/places/alley-wide.png",
                               "reverse": "refs/places/alley-reverse.png",
                               "landmark": "refs/places/alley-landmark.png"},
                     "light": "a sodium lamp on the left wall, high; the far end is dark"}}
```

- `wide`: one clean establishing picture showing the whole geography (walls, doors, scale). The anchor.
- `reverse`: a second picture from about 90 degrees round, so reverse and over-the-shoulder shots can be checked.
- `landmark`: a close-up of one thing the audience would notice if it moved or vanished.
- `light`: one line, the practical light source and which side it is on. Say it in exactly these words in every
  prompt for the place: a paraphrase makes the model flip it.

Draw the places empty of people (and of face posters on the walls: put "poster, portrait, face, character art" in the
negative prompt for scenery). One sheet per distinct place, not per scene.

## What the kit does about it

| Where | What |
|---|---|
| `lint` PL1 (blocks) | Every registered place has the three pictures (each a file in the film folder) and a `light` note. |
| `lint` PL2 (blocks) | A shot whose `scene:` names a registered place has that place's `wide` picture in its still's refs: attach the picture, never re-describe the place. |
| reference slots | Place first, character second, props last. |
| eval | A changed place picture makes a saved eval report stale. |

A shot names its place with `scene:` in the shot list (the tag already means "shots of one scene share a master still").
When a shot's best frame is better than the anchor, update the anchor with it, and say so in the notes: references do
not carry from one generation to the next by themselves.
