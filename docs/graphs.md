# ComfyUI graphs shipped with the kit

The graphs live in `src/atomic_flix/workflows/` and are ComfyUI API-format JSON (export with "Save (API Format)").
The kit fills a graph's `$placeholders` per take. A graph that declares other placeholder names is read through a
name map, `<graph>.map.json` next to it (see `runner/names.py`; extra map folders go in `ATOMIC_FLIX_MAPS`).
Each graph's models must be installed in your own ComfyUI; the kit does not download any. Check each model's
licence before release work; the open video models' licences ask that output be labelled as AI-generated.

| Graph | Does | Placeholders | Models it loads |
|---|---|---|---|
| `still.json`, `still2.json`, `still3.json` | A first frame from one, two or three reference pictures (image edit) | `$prompt $seed $width $height $image1..3` | Qwen-Image-Edit 2511 (fp8), Qwen 2.5 VL 7B text encoder, Qwen-Image VAE |
| `sung-ltx23-pinned.json` | A sung take on LTX-2.3: first frame also pinned as last frame, the window's vocal as audio | `$prompt $seed $width $height $frames $seconds $audio $first_frame` | ltx-2.3-22b-dev fp8, ltx-2.3 distilled LoRA, spatial upscaler x2, Gemma 3 12B text encoder |
| `sung-ltx23-pinned-soft.json` | The same with a softer pin | same | same |
| `sung-ltx23.json` | A sung take with no pinned last frame | same | same |
| `sung-ltx25-pinned.json` | A sung take on LTX-2.5 (int8) | same | LTX-2.5 distilled transformer, audio and video VAEs, latent upscaler, Gemma 4 12B |
| `plate-ltx23.json`, `plate-ltx23-pinned.json` | A silent plate (no audio) from a first frame, optionally pinned | `$prompt $seed $width $height $frames $first_frame` | LTX-2.3 set as above |
| `scail2-replace.json` | Replace the performer in a video (a Blender plate) with a character: SCAIL-2 pose-driven replacement with SAM matting | `$video $character $prompt $seed $width $height $frames` | Wan 2.1 SCAIL-2 int8, its DPO LoRA, Wan 2.1 VAE, umt5 xxl, clip vision h, lightx2v step-distill LoRA, SAM 3.1 |

Sizes: control-video and LTX graph sizes are multiples of 128 (`sizes.py`); SCAIL and Wan graphs take multiples of 32.
Measured on one RTX 3090 (see `docs/real-run.md`): a 6 s sung take at 1280x704 is about 96 GPU seconds with the
model warm, and one LTX load commits about 28 GB of host memory, so run one LTX load at a time unless your commit
headroom is much larger (`ATOMIC_FLIX_COMMIT_HEADROOM_GB` overrides the reading).

To add a graph: export it in API format, use `$names` for what changes per take, add `<graph>.meta.json` with
`commit_gb` (a graph with no sidecar is treated as heavy and runs alone), and add a `.map.json` if your names differ.
