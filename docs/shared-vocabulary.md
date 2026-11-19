# Shared vocabulary: what the similarity check does not count, and why

`tools/similarity.py` compares this tree with the earlier code. Some words and phrases are bound to appear in both
because a standard, a tool or plain English fixes them. This page lists every one of them; the tool reads its lists
from its own constants (`STANDARD_WORDS`, `STANDARD_KEYS`, `STANDARD_PHRASES`) and a test checks that each entry is
written here. Nothing on this page hides a number: the report prints the strict count (every name and key after the
original stop-list) next to the measure that decides PASS.

## Distinctive names and keys

The name and key measures count only distinctive entries:

- a name of six letters or more, or with an underscore inside it (`opening_still`, `go_on`); a leading or trailing
  underscore is Python's privacy mark and does not count, so `_ask` is the three-letter word `ask`;
- a key or flag of six letters or more after its leading dashes, or with an underscore or hyphen inside it.

Short words (`act`, `at`, `best`, `cost`, `cut`) are what any program in any domain names its variables, so a match
says nothing about copying. They stay in the strict number.

There is no allow-list. Every name and key the kit shares with the earlier code counts, including those a spec
mentions: the specs were written by people who had read the earlier tools, so a name they give may be that code's
vocabulary. Where a spec named a key, a value or a command, the kit uses a name of its own (the maintainers' renames table, kept privately in `docs/private/`,
lists each one). `tools/similarity.py --allow FILE` still exists for a one-off look at what a list would hide; a release
check never passes it.

## STANDARD_WORDS (identifiers)

| Words | Why they are standard |
|---|---|
| channels, samples, sample_rate, stereo, loudness, envelope, spectrum, onsets, decibels | The terms of digital audio: every WAV reader has channels and samples, every level meter reads loudness in decibels, onset and spectral envelope are signal-processing textbook names. |
| frames, pixels, duration, bitrate, height, codec | The terms of digital video, and the field names ffmpeg and ffprobe use. |
| camera, framing, cutaway | Film grammar: a shot has a camera and a framing; a cutaway is the editor's word for a shot away from the subject. Our specs use them as such. |
| downbeat, chorus, lyrics, tempo | Music terms with one meaning. |
| content, headers, status, timeout, request, response | HTTP's own vocabulary (Python's `urllib` and `http` use the same words). |
| clip_end, engine, material, smooth | Attribute names in Blender's Python API that `scenes/blender_run.py` must assign: a camera's `clip_end`, the scene's `render.engine`, a material slot's `material`, a mesh face's `smooth`. Blender fixes them; the kit's own scene format calls these `far`, `renderer` and `surface`. |
| before, behind, during, within, without, inside, around, toward, towards, through, between, beyond, across, against, unless, whether, already, always, enough, rather | English function words of six letters or more: prepositions, conjunctions and adverbs that name a position or a condition, never a design. |

## STANDARD_KEYS (JSON keys and command-line flags)

| Keys | Why they are standard |
|---|---|
| avg_frame_rate, r_frame_rate, nb_frames, duration, format, streams, width, height, codec_name, pix_fmt | ffprobe's JSON output fields; any program that reads ffprobe reads these names. |
| Content-Type, Content-Length | HTTP headers (RFC 9110). |
| prompt, client_id, prompt_id, class_type, inputs, outputs, images, filename, subfolder, status_str, completed, messages, exec_info, queue_running, queue_pending, system_stats, devices, vram_total, vram_free, status | ComfyUI's HTTP API: the request and response fields of `/prompt`, `/history` (its `status` object holds `status_str`, `completed` and `messages`), `/queue`, `/view` and `/system_stats`. A client has to use them. The kit's own files do not use `prompt` or `status` as names of their own except where they hold ComfyUI's answer, and the first film's lesson data keeps `prompt` as the key of a prompt's text. |
| cycles | Blender's Python API: the key of the Cycles add-on in `bpy.context.preferences.addons`, read to choose the GPU device. The kit's own name for that renderer is `pathtrace`. |
| fps, frames, seconds, channels, sample_rate, bpm, lufs | Units and media fields with one meaning everywhere. |
| --dry-run, --timeout, --force, --host, --port, --seed, --fps, --width, --height, --limit | Flags with the same meaning in most command-line tools. |

## STANDARD_PHRASES (prose)

These phrases are cut out of docstrings, comments and text before sentences and 6-word runs are formed, and no run
crosses the cut. The words around them are still compared.

| Phrase | Why it is standard |
|---|---|
| WCAG 2.3.1, WCAG 2.3.1's, general flash threshold, red flash threshold, red flash rule | The name and the terms of the W3C success criterion the flash check implements (Three Flashes or Below Threshold). |
| relative luminance, linearised sRGB, linearized sRGB | The WCAG and IEC 61966-2-1 terms for the brightness the flash check measures. |
| force_original_aspect_ratio=increase, force_original_aspect_ratio=decrease | ffmpeg `scale` filter options, spelled as ffmpeg spells them. |
| bicubic+accurate_rnd+full_chroma_int+bitexact | ffmpeg's swscale flags; our specs require this exact set for every rescale. |
| setpts=PTS-STARTPTS, -fps_mode passthrough | ffmpeg filter and option text. |
| integrated loudness, true peak, sample peak, loudness range, LUFS, dBFS, dBTP, LU | EBU R 128 and ITU-R BS.1770 loudness terms and units. |

## Changing a list

Add an entry only when it is fixed by a standard, a tool's interface or plain English, add its row here in the same
change, and say why. The strict number in the report will still count it.
