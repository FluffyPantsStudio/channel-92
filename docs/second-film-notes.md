# What the kit learned on a second song (2026-11-19)

The first real run of the kit on a song it had not been built against (a 4:51 song, ten Suno stems at 177 BPM, a
drum stem, a lead vocal stem). No lyrics or audio are kept here.

- **Pass the tempo when the stems name it.** With no hint the bar stage chose 88.5 BPM, half the true 177. Its "bar" was
  then two real bars, it reported phase changes at 0:46 and 3:54 and could not tell the one from the two (margin 0.13 z).
  With `atomic-flix bars FILM --bpm 177` it found a steady 176.82 BPM grid (beat spacing std 8 ms), no phase changes
  and a margin of 0.99 z. Stems from a generator usually carry the tempo in the file name: use it.
- **Bar one still needs the ear.** The detector chose phase 0 (score 2.50) over phase 2 (2.06) and the person heard
  phase 2. Both are the same "pair" (one or three); the kit is weakest exactly there, as on the first film. Click clips
  on the four phases, 30 s from a stable verse, are the check. Keep clips inside one section: a clip across a section
  boundary made the person say "closest but not perfect" before the grid was fixed.
- **Word labels change the timing from a guess to a measurement.** Without labels 45 of 48 lines were `guess`; with
  faster-whisper large-v3 labels (390 words) 46 were placed by level and 2 by guess. Labels are dated early by up to
  1.8 s, which the kit expects and flags, so the flagged count stays high (39 of 48) and those lines go to the ear.
  `tools/label_words.py` makes the labels. On Windows without CUDA 12 libraries (`cublas64_12.dll`) use `--device cpu`
  (about 13 minutes for large-v3 on a 4:51 vocal).
- **A scat line and a final repeated line get few labels** (5 of 13 and 1 of 4 words): expect `guess` there.
- **A mix longer than the stems.** The released mix was 0.25 s longer than the stems (a tail). Use the mix for the final
  sound and the stems for analysis; check the two start together.
