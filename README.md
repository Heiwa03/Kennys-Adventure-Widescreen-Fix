# Shark Attack / Kenny's Adventure — Widescreen Patch

Hor+ widescreen support for **Shark Attack** (a.k.a. *Kenny's Adventure: In
Search of Family Treasures*, *Scuba in Aruba*), DivoEngine v1.20 by DivoGames
(2007). Run the game at 1920x1080 — or any widescreen resolution up to 4K and
ultrawide — and see **more of the level**: correct proportions, no stretching,
no cropped vertical view.

The patcher byte-verifies your executable before touching it, keeps a backup,
and reverts with one command.

## Requirements

- Windows, with a working install of the game (32-bit Direct3D 8 title; runs
  fine on modern Windows)
- The **v1.20** executable — MD5 `8213f8a73ab2b728cd9421ac1eecc43c`
  (606,208 bytes). Anything else is rejected on purpose (see
  [Compatibility](#compatibility)).
- Python 3.6+ (standard library only)

## Quick start

1. Copy `widescreen_patch.py` into your game folder (next to
   `SharkAttack.exe`).
2. Open a terminal in that folder and run:

   ```
   python widescreen_patch.py
   ```

   It verifies the executable, saves `SharkAttack.exe.orig`, and applies the
   patches. Re-running is safe; `--status` shows the current state.

3. Pick a resolution — either:
   - in game: **Options → Resolution** (widescreen modes are listed now), or
   - in `Config.cfg`: set `nWidth`, `nHeight`, `bFullscreen`.

4. Play.

To undo everything:

```
python widescreen_patch.py --revert
```

`Config.cfg` is never touched by the patcher and is not restored by revert.

## What it changes

The engine is resolution- and aspect-independent by design: the renderer
(`RenderD3D8.dll`) already enumerates every mode your GPU supports, and the
camera, sprite culling and projection all derive from a per-mode "virtual
screen". Only two things in `SharkAttack.exe` limited widescreen, and the
patch changes exactly those (plus a version-string credit). Every byte it
touches is listed under [Patch details](#patch-details).

### 1. Widescreen field of view (Hor+)

The engine maps every display mode to a **virtual screen** — the view size in
world units — clamped between design bounds 640x480 and 1024x768
(`SetVideoMode`, at `0x409890` in the unpatched exe):

```
if (w < 640 || h < 480)          scale = max(640/w, 480/h)    // scale tiny modes up
else if (w <= 1024 && h <= 768)  scale = 1.0                  // native design window
else                             scale = min(1024/w, 768/h)   // large modes
virtual = (w*scale, h*scale)
```

The camera (`0x408CC0`), sprite culling (`0x40A7E0`) and projection
(`0x4115B0`) all use the virtual screen size directly. The `min()` in the
large-mode branch caps the *horizontal* view at 1024 world units, so on
widescreen displays the game zooms in and **crops the vertical view**
(1920x1080 showed a 1024x576 slice of the world).

The patch raises the max-design-**width** constants so the scale becomes
height-based (`768/h`): the vertical view is always the full 768 units —
exactly what the original game shows at 1024x768 — and widescreen modes see
further left/right. 4:3 resolutions are unaffected.

| Display mode | Original engine | Patched |
|---|---|---|
| 800x600 | 800x600 | 800x600 (unchanged) |
| 1024x768 | 1024x768 | 1024x768 (unchanged) |
| 1280x800 | 1024x640 (cropped) | **1228.8x768** |
| 1280x720 ¹ | 1024x576 (cropped) | **1280x720** |
| 1920x1080 | 1024x576 (cropped) | **1365.3x768** |
| 1920x1200 | 1024x640 (cropped) | **1228.8x768** |
| 2560x1440 | 1024x576 (cropped) | **1365.3x768** |
| 3440x1440 (21:9) | 1024x576 (cropped) | **1834.7x768** |

¹ 720p falls inside the scale-1.0 window (height ≤ 768), so its view is
1280x720 — slightly less vertical world than 768-tall views, the same
treatment the original gives to sub-768 modes.

### 2. Options-menu resolution list

The in-game Options screen only offered modes present in a hardcoded 6-entry
table (`0x479628`: 640x480 / 800x600 / 1024x768, 16 & 32 bpp). The patch
writes a 20-entry table (common 4:3, 16:9, 16:10 and 21:9 modes, 32 bpp, up
to 3840x2160) into unused `.rdata` space and repoints the scan loop. The menu
now lists every widescreen mode that is *both* in that list *and* exposed by
your GPU. Missing an exotic one? Add it to `MODES_32BPP` in the script and
re-run.

### 3. Version credit

The engine draws the `<Info version="...">` value from `data\Settings.xml` at
the bottom-left of the main menu. The patch sets it to:

```
v 1.20 + Widescreen patch by Heiwa
```

(Edit `NEW_VERSION` in the script if you'd rather credit it differently.)

## Patch details

Every change to `SharkAttack.exe` (virtual addresses; file offset =
VA − 0x400000 for `.text`/`.rdata`):

| VA / file offset | What | Original | Patched |
|---|---|---|---|
| `0x47DC10` | double, max design width | 1024.0 | 100000.0 |
| `0x47DC1C` | float, same constant (scale-1.0 window) | 1024.0 | 100000.0 |
| `0x41D14D` | `MOV EAX` imm — whitelist scan start | `0x479630` | `0x48AB08` |
| `0x41D169` | `CMP EAX` imm — whitelist scan end | `0x479690` | `0x48AC48` |
| `0x48AB00` | 320 bytes of `.rdata` padding | zeros | 20-entry mode table |
| file `0x218` | `.rdata` section `VirtualSize` | `0x13AA8` | `0x14000` |

Everything else in the executable is byte-identical. The only data file
modified is `data\Settings.xml` (the `version` attribute). The old 6-entry
table at `0x479628` is left in place but no longer referenced.

## Compatibility

- Verified against the v1.20 executable only (MD5 above). The patcher
  verifies all original bytes and aborts on any mismatch — other builds
  (different localizations, other DivoGames titles) will be rejected until
  the offsets are re-derived; the [Patch details](#patch-details) table and
  the function addresses above are the starting point for that.
- Tested on Windows 10 (64-bit) with an AMD Radeon iGPU, at native 1280x800
  and GPU-scaled 1920x1080, plus a 10-minute soak at the main menu. The
  in-game level view and the Options → Apply flow were exercised but not
  exhaustively tested — if you hit a problem, open an issue.

## Known quirks

- **Alt-tab at non-native exclusive modes.** Like many 2000s Direct3D 8
  titles, the engine's device-lost recovery is unreliable when the requested
  fullscreen mode is not the display's native mode (the driver GPU-scales
  it): the game may drop to a window or reset `Config.cfg`. This is stock
  behavior — reproducible on the unpatched exe — and is avoided by using
  your display's native resolution.
- **Keep `Game.bin`.** Player profiles live in `Game.bin`; `Config.cfg` holds
  the per-profile video settings. If `Game.bin` is missing, the engine
  silently falls back to a default profile (800x600) and *ignores* the
  resolution in `Config.cfg`. The game creates this file itself on a clean
  exit — so if you ever lose it, launch once and quit properly to regenerate
  it.
- **16-bpp menu entries were dropped** from the whitelist — modern GPUs
  enumerate 32-bpp modes anyway. Requesting 16 bpp still works and resolves
  to a 32-bpp backbuffer.

## How it was verified

- The engine's virtual-screen globals were read from the running process:
  1920x1080 → 1365.33x768 and 1280x800 → 1228.8x768 after the patch
  (1024x576 / 1024x640 before).
- The Options screen's resolution list was read from process memory: 12
  entries on the test GPU (640x480 through 1920x1080 up to 2560x1600),
  versus the original six 4:3 modes.
- The version string was read from the engine's display global and confirmed
  rendering on screen.

## License

This patch is released under the **GPL-3.0** license — see `LICENSE`.

*Shark Attack*, *Kenny's Adventure* and *Scuba in Aruba* are © 2003-2007
DivoGames. This project is not affiliated with or endorsed by DivoGames. You
must own a copy of the game; the patch contains no game assets and modifies
only your local installation.

Patch by Heiwa.
