# Channel 92's eras

Channel 92 broadcasts from 1950 to 2010. A film's year (`atomic-flix choose FILM year YYYY`) picks its era, and a
year between two eras' first years blends their looks ("Years between eras" below); `finish --year YYYY` sets another
year for one run, `finish --era ID` lays that era's own look on, and a film with none of them has no era and is
finished without a look. Each era's look is laid on only in the final (`cuts/vNN-final.mp4`); the cut and the graded
cut stay clean.

| Era | Years | The medium | Before ntsc-rs (ffmpeg) | ntsc-rs preset | Suggests | Logo | Intro |
|---|---|---|---|---|---|---|---|
| `1950s` | 1950 to 1959 | Black-and-white kinescope: the broadcast filmed off a studio monitor, soft, with hum bars and flicker | monochrome; after ntsc-rs the kinescope: two soft hum bars rolling up, a faint flicker, faint scan lines, a glow on bright areas, strong corner falloff, milky blacks and clipped highlights, monochrome again | soft (negative sharpening, heavy luma smear), ringing, composite noise, no colour noise, no tape | 4:3 | engraved serif on a light card, the 92 hatched | monochrome test card: rings, grid, grey steps |
| `1960s` | 1960 to 1969 | Early colour broadcast: heavy colour smear, colour a little off | none | the strongest colour delay and colour noise, a small phase error, vertical colour blend | 4:3 | heavy sans in cream on a charcoal plate, a strip of teal, red and mustard blocks below the letters | colour blocks laid down one by one on cream |
| `1970s` | 1970 to 1979 | Analog colour broadcast: dot crawl on sharp edges, ringing, warm colour | a warm colour balance | notch demodulation (dot crawl), ringing, moderate noise | 4:3 | rounded cream letters with brown, orange and amber outlines | brown to orange with stacked warm stripes |
| `1980s` | 1980 to 1989 | Home tape, VHS and Betamax: tape noise, head switching, tracking lines | none | VHS at SP, head switching, tracking noise, edge wave, chroma loss | 4:3 | chrome 92, neon pink CHANNEL | neon grid floor under a purple to pink sky |
| `1990s` | 1990 to 1999 | A worn VHS camcorder tape: long play, wavy edges, colour loss | none | VHS at LP, more edge wave, chroma loss and noise, head switching starting mid-line | 4:3 to 1997, 16:9 from 1998 | white letters with a cyan and magenta split, slices knocked sideways | black with cyan and magenta bars, a colour-split glitch |
| `2000s` | 2000 to 2010 | Late analog cable into early digital: mild composite noise | none | mild composite noise, 2D comb demodulation, little smear, no tape | 16:9 | the channel's own modern mark | clean digital blue, a glossy silver bevelled plate |

The suggested aspect comes from the aspect table (`aspects.suggested_aspect`, 16:9 from 1998); it is only ever a
suggestion. ntsc-rs works at 480 lines on the frame's short side for every era (`--scale 480` for a wide frame, 853 for
a 9:16 one, so it keeps 480 across) and the final is scaled back to the film's size.

Files:

- the eras: `src/atomic_flix/eras.py`
- the presets: `src/atomic_flix/looks/<era>.json`, checked against `looks/__init__.py` (docs/third-party.md says
  where the schema came from)
- the logos: `src/atomic_flix/brand/eras/logo-<era>.png` (the 2000s use `brand/channel92-logo.png`), drawn with
  real fonts by `tools/make_era_logos.py` (needs Pillow: `pip install -e ".[brand]"`). The words are always
  CHANNEL and 92; the marks are Channel 92's own and imitate no real network's
- the intros: `src/atomic_flix/brand/era_intro.py`, ffmpeg only, 5 seconds, silent, made at the film's own frame size
  and kept in the film's `brand/` folder

To approve an era by eye before the batch: `atomic-flix finish FILM --sample still.png` writes
`plan/look-sample.png`, one frame of the era's look and logo on that still.

## Years between eras

Each era's preset and filters are the look of its decade's first year, the anchor: 1950, 1960, 1970, 1980, 1990,
2000. A year at an anchor gets that era's look exactly; 2000 to 2010 have no later anchor and get the 2000s look
exactly. A year between two anchors blends the two neighbouring looks by the fraction of the way, the weight: 1975
is halfway between the 1970s and the 1980s, 1956 is 60 percent of the way from the 1950s to the 1960s, 1996 is 60
percent of the way from the 1990s to the 2000s. `progress` and `finish` say it in one line, always from the year's
own decade ("year 1956: the 1950s look, 60 percent of the way to the 1960s", "year 1975: halfway between the 1970s
and the 1980s looks"). The logo and the intro are never blended: they follow the decade the year belongs to (1956
and 1959 wear the 1950s mark, 1960 the 1960s mark). `finish --era ID` always lays that
era's own look on, with no blend. No file in `looks/` changes: the blend is worked out at each run
(`eras.year_look`, `looks.blend_presets`) and written into the finish work folder, which goes when the run ends.

The preset, setting by setting, by its kind in the schema (`looks/__init__.py`):

- numbers and shares: linear between the two
- the one angle, `chroma_phase_error` (a fraction of a turn, which ntsc-rs wraps): the short way round the circle,
  wrapped back into 0 to 1. The 1960s 0.985 is a few degrees the other way from 0, so 1950 to 1960 stay within 0.015
  of a turn of 0; a straight line would pass through 0.5 and turn every hue round (red hair green). No other setting
  is cyclic: `chroma_phase_noise_intensity` is how much the phase jitters, not an angle
- whole numbers (heights, detail levels, the vertical colour delay): linear, then rounded
- menu choices and the seed (demodulator, filter type, luma filter, lowpass, tape speed, field, `random_seed`): the
  nearer anchor's; a tie (a year ending in 5) goes to the later era
- switch groups: a switch and its members (composite noise, snow, head switching, tracking noise, ringing, luma
  noise, chroma noise, the VHS settings with their sharpening and edge wave inside, and the scale settings). Snow has
  no switch of its own and counts as on while its intensity is above 0
  - on at both anchors: the members blend by kind (a group inside, such as the VHS edge wave, by these same rules)
  - on at one anchor: the group is on once that anchor's weight reaches 0.2, with every member from that anchor and
    its strength members scaled by the weight, so the effect fades in or out instead of switching; below 0.2 it is
    off and taken whole from the other anchor
  - off at both: off, taken whole from the nearer anchor

The strength members (`looks/blend.py`, `STRENGTH`), scaled toward the value at which they do nothing (0, or 1 for
the two scales): `composite_noise_intensity`, `snow_intensity`, `head_switching_height`,
`head_switching_horizontal_shift`, `tracking_noise_height`, `tracking_noise_wave_intensity`,
`tracking_noise_snow_intensity`, `tracking_noise_noise_intensity`, `ringing_scale`, `luma_noise_intensity`,
`chroma_noise_intensity`, `vhs_chroma_loss`, `vhs_sharpen`, `vhs_edge_wave`, `bandwidth_scale`, `vertical_scale`.
Every other member (frequencies, detail levels, offsets, the tape speed) keeps the on-side value.

The ffmpeg filters, built from the constants in `eras.py` and the weight alone (nothing else from film.json reaches a
filter):

- the 1950s monochrome fades into colour between 1950 and 1960: the colour kept is the weight toward the 1960s
  (1951 keeps a tenth, 1955 half, 1956 six tenths); 1950 is fully monochrome
- the kinescope fades out over the same years: its hum, flicker and scan-line depths, the glow's opacity, the
  vignette's angle and the tone curve's pull all scale by the 1950s weight (full in 1950, half in 1955). Below full
  strength it leaves out its final grey, so the colour the pre-filter let in stays; from 1960 on there is none
- the 1970s warm lift scales by the 1970s weight, the same both ways: none in 1960, rising to full in 1970, falling
  to none in 1980 (half in 1965 and in 1975)

| Year | The line | Logo and intro | Before ntsc-rs | After ntsc-rs | Groups that fade |
|---|---|---|---|---|---|
| 1950 | the 1950s look | 1950s | monochrome | the kinescope | none |
| 1951 | the 1950s look, 10 percent of the way to the 1960s | 1950s | a tenth of the colour | the kinescope at 90 % | ringing, chroma noise and VHS still off (under 0.2) |
| 1955 | halfway between the 1950s and the 1960s looks | 1950s | half the colour | the kinescope at half | ringing, chroma noise at half; the VHS colour blend on |
| 1956 | the 1950s look, 60 percent of the way to the 1960s | 1950s | six tenths of the colour | the kinescope at 40 % | ringing, chroma noise at 60 % |
| 1965 | halfway between the 1960s and the 1970s looks | 1960s | the warm lift at half | none | the scale settings at half |
| 1971 | the 1970s look, 10 percent of the way to the 1980s | 1970s | the warm lift at 90 % | none | head switching, tracking noise, tape still off |
| 1972 | the 1970s look, 20 percent of the way to the 1980s | 1970s | the warm lift at 80 % | none | head switching, tracking noise, snow and tape on at 20 % |
| 1975 | halfway between the 1970s and the 1980s looks | 1970s | the warm lift at half | none | head switching, tracking noise, snow and tape at half |
| 1987 | the 1980s look, 70 percent of the way to the 1990s | 1980s | none | none | head switching and tracking noise at 30 % |
| 1996 | the 1990s look, 60 percent of the way to the 2000s | 1990s | none | none | the VHS tape at 40 % |
| 1999 | the 1990s look, 90 percent of the way to the 2000s | 1990s | none | none | the VHS tape off (under 0.2) |
| 2000 to 2010 | the 2000s look | 2000s | none | none | none |

To see what a year is made of while tuning: `python tools/blend_demo.py 1956` prints the pair, the weight, the
filters and every setting that differs from the nearer era's preset.

## How the presets were tuned (2026-11-20)

The six presets were tuned on real renders with the real ntsc-rs 0.9.7, not from setting names alone. Test clip: six
seconds with a face close-up and a street shot. For each era one agent made a control (the earlier preset) and five
variants, rendered through `finish`'s own chain; a separate judge that saw only pictures scored each candidate 1 to 5 on
five points (does it read as that medium, is the face readable, are the artefacts natural, is the logo legible, would a
director keep the frame); a candidate survives only with every score at 3 or more. Two to four rounds each, the next round
built from the judge's words.

What the rounds found, which the presets now carry:

- `composite_preemphasis` is the one setting that moves colour: on a neutral preset 0.5 took a skin patch from RGB
  (132, 85, 67) to (142, 83, 51), orange. The first presets used 0.5 to 1.0 and every era looked orange. The survivors
  keep it at 0 or about a third of the old value (`tests/eras` guards this).
- No ntsc-rs setting is a saturation or black-level control; warmth in the 1970s and 1950s tone belongs to the kit's
  ffmpeg pre and post filters.
- The snow setting makes the 1990s dropout dashes (its count and its horizontal length are the same two numbers).
- A long chroma delay widens the 1960s colour bleed but pulls colour blocks off their letters. The first 1960s logo
  set cream numerals on a red block, and the delay slid the block's colour off them so the mark read "922". The logo
  is now read by light against dark: cream letters on a near-neutral charcoal plate, with its colour in a strip of
  blocks below the letters, in rows of its own, where a sideways smear only runs the strip a little past the plate's
  edge (`tests/brand` checks the letter rows are colourless and the letters stand well above the plate in luma).
- The 1970s dot crawl is held at the edge of what the lip line tolerates: more crawl turns the lips into a checkerboard.

Not settled, and not ntsc-rs's to settle:

- 1950s: a kinescope also wants corner falloff, halation, milky blacks and slow hum bars, which ntsc-rs cannot make.
  They are now in the era's post-filter (`eras.py`, `KINESCOPE`), tuned on the same clip in a later round
  (2026-11-20) and measured part by part in `tests/eras/test_era_filters.py`.
- Judged on stills only: nothing was watched in motion (tracking bands, flicker, dropout movement, flash).
