# Third-party programs the kit runs

## ntsc-rs

[ntsc-rs](https://github.com/ntsc-rs/ntsc-rs) emulates analog video: NTSC composite artefacts, VHS tape noise,
head switching, tracking errors, colour smear. `finish` runs it to lay each Channel 92 era's look on a finished
film (docs/eras.md). It is written in Rust by its own authors; the kit has no part in it.

**How we use it: we only run it.** The kit never bundles, links or copies ntsc-rs into itself or a release of
it. `channel92 setup --install` fetches the project's own pinned build, with your yes, as a separate program in a
per-user folder (below); `finish` and every other verb never download anything. The kit calls its command-line
program, `ntsc-rs-cli`, as a separate process. Without it `finish` still delivers the film, without the era look,
and says so in one sentence: run `channel92 setup --install`.

**Licences, as found in its repository (tag v0.9.7, read 2026-11-20):**

- `LICENSE-MIT`, `LICENSE-APACHE-2.0`, `LICENSE-ISC` at the top. The MIT text says it applies to all source files
  except those under `crates/gui`. The effect library, `crates/ntscrs/Cargo.toml`, declares
  `MIT OR ISC OR Apache-2.0`.
- `crates/gui/LICENSE` is the GNU GPL version 3, and `crates/gui/Cargo.toml` declares `GPL-3.0`. The command-line
  program `ntsc-rs-cli` is built from that crate (`crates/gui/src/bin/ntsc-rs-cli.rs`), so the program we run is
  GPL-3.0. Running a GPL program as a separate process does not bring its licence onto the kit, which is why we
  run it and never bundle or link it. If you redistribute ntsc-rs yourself, follow its licences.
- The standalone Windows download bundles GStreamer, which ntsc-rs needs (its own docs, "Command-line interface":
  on Windows the program sits in the `bin` folder beside the GStreamer libraries; on Linux GStreamer is not
  bundled).

**Install it with the kit:** `channel92 setup` shows whether it is found; `channel92 setup --install` installs it.

| | |
|---|---|
| Version | v0.9.7, pinned in `src/atomic_flix/prereq/pins.py` (never trusted on first use) |
| Source | `https://github.com/ntsc-rs/ntsc-rs/releases/download/v0.9.7/ASSET`, HTTPS only, hosts `github.com`, `objects.githubusercontent.com` and `release-assets.githubusercontent.com` only (redirects included), no credentials sent |
| Windows | `ntsc-rs-windows-standalone.zip`, 77630964 bytes, sha256 `4f19c6f424058e8c516687126e5b63fcc44d07daa89e75911adb494c9e8874e6` |
| Linux | `ntsc-rs-linux-standalone.zip`, 14568231 bytes, sha256 `968fdb21d1d34d53004e7f822d941ba6a93b1cce067e492d2095f071d43567d1` |
| macOS | `ntsc-rs-macos-standalone.pkg`, 90556245 bytes, sha256 `51ca362a9ce8b40cb47804959cbbdc5bb71e79c0f334542dd85fa27faa04c1e0`: an installer package the kit does not run; `setup --install` prints its address, hash and the manual step |
| Destination | Windows `%LOCALAPPDATA%\Channel92\tools\ntsc-rs\0.9.7`, Linux `~/.local/share/channel92/tools/ntsc-rs/0.9.7`, macOS `~/Library/Application Support/Channel92/tools/ntsc-rs/0.9.7`; `CHANNEL92_HOME` replaces the base. Outside every repo and film folder |

What `--install` does: it prints the asset, address, size, destination and the licence note, and goes on only with
`--yes` or a typed `yes` at a terminal (piped input is never read as a yes). It downloads to a partial file, checks
the size and then the sha256 against the table (a mismatch is refused, says expected and got, and is deleted),
unpacks into a staging folder while refusing any entry that is absolute, names a drive, climbs with `..`, is a link
or lands outside the folder, finds `ntsc-rs-cli` by walking what was unpacked (on Windows it sits in
`ntsc-rs-windows-standalone\bin\`), runs it with `--help`, writes `channel92-install.json` beside it and only then
moves the folder into place. A failure at any step leaves nothing behind. Run again, it says the tool is already
installed and does nothing.

Where the kit finds it, in order: `finish --ntsc-rs PATH`, `CHANNEL92_NTSC_RS`, the kit tools folder (the newest
finished install), then `ntsc-rs-cli` on the PATH.

**Or install it yourself:** download the standalone build from <https://github.com/ntsc-rs/ntsc-rs/releases>, unpack
it, and pass `--ntsc-rs path/to/bin/ntsc-rs-cli.exe`, set `CHANNEL92_NTSC_RS`, or put its folder on the PATH.

Check it: `channel92 finish FILM --sample still.png` writes `plan/look-sample.png` with the era's look.
`pytest -m ntsc_rs` runs the one test that uses the real program (it skips when none is found);
`CHANNEL92_NETWORK_TESTS=1 pytest -m network` downloads the real pinned Linux asset and checks its hash.

### The command we run

From `crates/gui/src/bin/ntsc-rs-cli.rs` (v0.9.7) and the docs page <https://ntsc.rs/docs/command-line-interface/>:

```
ntsc-rs-cli -i IN.mkv -o OUT.mkv -p PRESET.json -y -c ffv1 --scale LINES
```

| Flag | What it does there |
|---|---|
| `-i`, `-o` | input and output; required |
| `-p`, `--settings-path` | a JSON preset file (`-j` takes the JSON inline instead) |
| `-y`, `--overwrite` | overwrite without asking (`-n` never overwrites; with neither it asks at a terminal) |
| `-c`, `--codec` | `h264` (default, `.mp4`), `ffv1` (lossless, `.mkv`) or `png` (an image sequence) |
| `--scale LINES` | resize the input to that many lines before the effect; its own settings advise scaling to 480p for results that look right |

Other flags it has and we leave at their defaults: `--fps` and `--duration` (still images), `--scale-filter`
(`nearest`, `bilinear` default, `bicubic`), `--interlace`, `--chroma-subsampling`, `--quality` (H.264, 0 to 50,
default 27), `--encoding-speed` (H.264, 0 to 8, default 5), `--bit-depth` (FFV1: 8, 10, 12), `--compression-level`
(PNG, 0 to 9, default 6), `--single-frame-time` (PNG). It has no flag for threads.

We write FFV1 so the only lossy encode of the film stays ours (`finish/chain.py`). The kit hands ntsc-rs a silent
lossless file and takes the sound from the graded cut itself, since what ntsc-rs does with audio was not
established. Its output is scaled back to the film's size in the final encode.

### Where the preset schema came from

Read from ntsc-rs's source at tag v0.9.7, not guessed:

- `crates/ntscrs/src/settings/standard.rs`: every setting's key (`setting_id!(n, "key", ...)`), its kind and range
  (`SettingKind::FloatRange`, `IntRange`, `Percentage` 0 to 1, `Boolean`, `Group`, `Enumeration`), the menu
  numbers of each choice (the `#[repr(u8)]` enums: for example the tape speed is 0 none, 1 SP, 2 LP, 3 EP), and
  its defaults (`impl Default for NtscEffect`) and its oldest defaults (`legacy_value`).
- `crates/ntscrs/src/settings/settings.rs`: how a preset is read (`settings_from_json`, `from_json_generic`): one
  flat JSON object; a group's switch is a key of its own and its members sit beside it at the top level;
  `"version": 1` is required; ranges are clamped; enumerations are read as whole numbers; a missing key keeps the
  oldest default. That last rule is why every preset of ours gives all 60 keys.

The schema lives in `src/atomic_flix/looks/__init__.py` (`SETTINGS`, `check_preset`) and the presets are checked
against it by `tests/eras/test_looks_presets.py`.

**Not established:** what ntsc-rs does with an input's audio track, whether a progressive input is ever written
interlaced with the interleaved field settings (our presets use its default field setting, so this is its own
default behaviour), and the exact meaning of each value beyond its label and range. The presets' values are ours,
tuned by reading those labels; they have not yet been seen through the real program on this machine (it is not
installed here), so the first real run is a look by eye (`finish --sample`).
