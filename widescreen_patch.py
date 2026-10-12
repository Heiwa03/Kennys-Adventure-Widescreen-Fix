#!/usr/bin/env python
"""
Widescreen patch for Shark Attack / Kenny's Adventure (DivoEngine, DivoGames 2007).

What it does
------------
1. Hor+ widescreen field of view:
   The engine maps the display mode to a "virtual screen" (world-space view size)
   clamped between 640x480 and 1024x768 design bounds. For modes larger than
   1024x768 it picks scale = min(1024/w, 768/h), which caps the HORIZONTAL view
   at 1024 world units and CROPS the vertical view on widescreen displays
   (1920x1080 -> virtual 1024x576).
   The patch raises the max-design-WIDTH constants (double @0x47dc10,
   float @0x47dc1c) from 1024.0 to 100000.0 so the scale becomes height-based
   (768/h): widescreen modes now keep the full 768-unit vertical view and show
   MORE world horizontally (1920x1080 -> virtual 1365x768). 4:3 modes
   (800x600, 1024x768, 1600x1200) are unaffected.

2. Options-menu resolution whitelist:
   The video options screen only offers modes present in a hardcoded 6-entry
   table at 0x479628 (640x480/800x600/1024x768 x 16/32bpp). The patch writes a
   20-entry table (all common 4:3/16:9/16:10/21:9 modes at 32bpp) into unused
   .rdata slack at 0x48AB00, repoints the scan loop's start/end immediates
   (MOV EAX @0x41d14d, CMP EAX @0x41d169) and extends the .rdata VirtualSize.

3. Version credit in data\\Settings.xml:
   The engine draws the <Info version="..."> string at the bottom-left of the
   main menu (parsed by FUN_0040b320 into the wide-string global 0x48E154,
   rendered by FUN_004189e0 at (20, screenH-20)). Set to
   "v 1.20 + Widescreen patch by Heiwa".

Usage
-----
  python widescreen_patch.py            # patch (backs up SharkAttack.exe.orig)
  python widescreen_patch.py --revert   # restore original exe + Settings.xml
  python widescreen_patch.py --status   # show patch state
"""
import re
import struct
import sys
import shutil
import os

EXE = "SharkAttack.exe"
BACKUP = "SharkAttack.exe.orig"
SETTINGS = os.path.join("data", "Settings.xml")

ORIG_VERSION = "v 1.20"
NEW_VERSION = "v 1.20 + Widescreen patch by Heiwa"

# --- patch sites (file offsets == RVAs here: .text and .rdata are identity-mapped) ---
SCALE_DOUBLE_OFF = 0x7DC10          # double 1024.0 -> 100000.0  (max design width)
SCALE_FLOAT_OFF = 0x7DC1C           # float  1024.0 -> 100000.0f (max design width, scale==1.0 window)
TABLE_MOV_OFF = 0x1D14D             # b8 30 96 47 00  MOV EAX, 0x479630
TABLE_CMP_OFF = 0x1D169             # 3d 90 96 47 00  CMP EAX, 0x479690
RDATA_HEADER_OFF = 0x210            # section table entry for .rdata
NEW_TABLE_OFF = 0x8AB00             # file offset == RVA (inside .rdata raw data, was zero padding)
NEW_TABLE_VA = 0x48AB00

MODES_32BPP = [
    (640, 480), (800, 600), (1024, 768), (1152, 864),
    (1280, 720), (1280, 768), (1280, 800), (1280, 1024),
    (1360, 768), (1366, 768), (1440, 900),
    (1600, 900), (1600, 1200), (1680, 1050),
    (1920, 1080), (1920, 1200), (2048, 1536),
    (2560, 1440), (2560, 1600), (3840, 2160),
]

ORIG_SCALE_DOUBLE = struct.pack("<d", 1024.0)
ORIG_SCALE_FLOAT = struct.pack("<f", 1024.0)
ORIG_MOV = bytes.fromhex("b830964700")
ORIG_CMP = bytes.fromhex("3d90964700")
ORIG_RDATA_VSIZE = 0x13AA8
ORIG_TABLE = b"".join(struct.pack("<IIII", w, h, bpp, 0)
                      for w, h, bpp in [(640, 480, 16), (640, 480, 32),
                                        (800, 600, 16), (800, 600, 32),
                                        (1024, 768, 16), (1024, 768, 32)])

NEW_SCALE_DOUBLE = struct.pack("<d", 100000.0)
NEW_SCALE_FLOAT = struct.pack("<f", 100000.0)
NEW_TABLE = b"".join(struct.pack("<IIII", w, h, 32, 0) for w, h in MODES_32BPP)
TABLE_PTR_IMM = NEW_TABLE_VA + 8              # entries are read at EAX-8
TABLE_END_IMM = NEW_TABLE_VA + 8 + len(NEW_TABLE)
NEW_MOV = b"\xb8" + struct.pack("<I", TABLE_PTR_IMM)
NEW_CMP = b"\x3d" + struct.pack("<I", TABLE_END_IMM)
NEW_RDATA_VSIZE = (NEW_TABLE_OFF + len(NEW_TABLE) - 0x77000 + 0xFFF) & ~0xFFF


def check_site(data, off, expect, what):
    actual = data[off:off + len(expect)]
    if actual != expect:
        print(f"  ERROR: {what} @ 0x{off:X}: found {actual.hex()}, expected {expect.hex()}")
        return False
    return True


def is_patched(data):
    return data[SCALE_DOUBLE_OFF:SCALE_DOUBLE_OFF + 8] == NEW_SCALE_DOUBLE


def get_settings_version():
    """Return the current <Info version="..."> value, or None if unreadable."""
    try:
        txt = open(SETTINGS, "r", encoding="cp1251").read()
    except OSError:
        return None
    m = re.search(r'<Info\s+version="([^"]*)"', txt)
    return m.group(1) if m else None


def set_settings_version(value):
    # newline='' on both ends so CRLF/LF line endings survive the rewrite untouched
    txt = open(SETTINGS, "r", encoding="cp1251", newline="").read()
    new = re.sub(r'(<Info\s+version=")[^"]*(")', lambda m: m.group(1) + value + m.group(2), txt, count=1)
    if new == txt:
        return False
    open(SETTINGS, "w", encoding="cp1251", newline="").write(new)
    return True


def do_patch():
    if not os.path.exists(EXE):
        print(f"ERROR: {EXE} not found (run from the game folder)")
        return 1
    data = open(EXE, "rb").read()
    already = is_patched(data)
    ver = get_settings_version()
    if already and ver == NEW_VERSION:
        print("Already patched (exe + Settings.xml).")
        return 0

    if not already:
        rc = do_patch_exe(data)
        if rc:
            return rc
    if ver != NEW_VERSION:
        rc = do_patch_settings(ver)
        if rc:
            return rc
    return 0


def do_patch_exe(data):
    print(f"Verifying original {EXE} ({len(data)} bytes)...")
    ok = True
    ok &= check_site(data, SCALE_DOUBLE_OFF, ORIG_SCALE_DOUBLE, "scale double 1024.0")
    ok &= check_site(data, SCALE_FLOAT_OFF, ORIG_SCALE_FLOAT, "scale float 1024.0")
    ok &= check_site(data, TABLE_MOV_OFF, ORIG_MOV, "whitelist MOV EAX")
    ok &= check_site(data, TABLE_CMP_OFF, ORIG_CMP, "whitelist CMP EAX")
    ok &= check_site(data, 0x79628, ORIG_TABLE, "old whitelist table")
    ok &= check_site(data, RDATA_HEADER_OFF + 8, struct.pack("<I", ORIG_RDATA_VSIZE), ".rdata VirtualSize")
    slack = data[NEW_TABLE_OFF:NEW_TABLE_OFF + len(NEW_TABLE)]
    if any(b != 0 for b in slack):
        print(f"  ERROR: .rdata slack @ 0x{NEW_TABLE_OFF:X} is not empty")
        ok = False
    if NEW_RDATA_VSIZE > 0x14000:
        print("  ERROR: new .rdata vsize exceeds raw size")
        ok = False
    if not ok:
        print("Verification failed - file does not match expected v1.20 layout. Aborting.")
        return 1

    shutil.copy2(EXE, BACKUP)
    print(f"Backup saved: {BACKUP}")

    buf = bytearray(data)
    buf[SCALE_DOUBLE_OFF:SCALE_DOUBLE_OFF + 8] = NEW_SCALE_DOUBLE
    buf[SCALE_FLOAT_OFF:SCALE_FLOAT_OFF + 4] = NEW_SCALE_FLOAT
    buf[TABLE_MOV_OFF:TABLE_MOV_OFF + 5] = NEW_MOV
    buf[TABLE_CMP_OFF:TABLE_CMP_OFF + 5] = NEW_CMP
    buf[NEW_TABLE_OFF:NEW_TABLE_OFF + len(NEW_TABLE)] = NEW_TABLE
    struct.pack_into("<I", buf, RDATA_HEADER_OFF + 8, NEW_RDATA_VSIZE)

    open(EXE, "wb").write(bytes(buf))
    print("Patched:")
    print(f"  [1] FOV scale: max design width 1024 -> 100000 "
          f"(double @0x47DC10, float @0x47DC1C)")
    print(f"      1920x1080 virtual view: 1024x576 (cropped) -> 1365x768 (Hor+)")
    print(f"  [2] Options menu: {len(MODES_32BPP)} resolutions "
          f"(table @0x{NEW_TABLE_VA:X}, loop bounds repointed)")
    print(f"  [3] .rdata VirtualSize 0x{ORIG_RDATA_VSIZE:X} -> 0x{NEW_RDATA_VSIZE:X}")
    return 0


def do_patch_settings(current):
    if current is None:
        print(f"ERROR: could not read <Info version=...> from {SETTINGS}")
        return 1
    if set_settings_version(NEW_VERSION):
        print(f"Patched {SETTINGS}: version \"{current}\" -> \"{NEW_VERSION}\"")
        return 0
    print(f"ERROR: could not update <Info version=...> in {SETTINGS}")
    return 1


def do_revert():
    ok = 0
    if os.path.exists(BACKUP):
        shutil.copy2(BACKUP, EXE)
        print(f"Restored {EXE} from {BACKUP}")
    else:
        print(f"ERROR: {BACKUP} not found")
        ok = 1
    ver = get_settings_version()
    if ver is not None and ver != ORIG_VERSION:
        if set_settings_version(ORIG_VERSION):
            print(f'Restored {SETTINGS}: version -> "{ORIG_VERSION}"')
    return ok


def do_status():
    if not os.path.exists(EXE):
        print(f"ERROR: {EXE} not found (run from the game folder)")
        return 1
    data = open(EXE, "rb").read()
    if is_patched(data):
        print(f"{EXE}: PATCHED")
    elif data[SCALE_DOUBLE_OFF:SCALE_DOUBLE_OFF + 8] == ORIG_SCALE_DOUBLE:
        print(f"{EXE}: original (unpatched)")
    else:
        print(f"{EXE}: UNKNOWN contents at scale site")
    ver = get_settings_version()
    print(f"{SETTINGS}: version = \"{ver}\" "
          f"({'patched' if ver == NEW_VERSION else 'original' if ver == ORIG_VERSION else 'custom'})")
    print(f"backup {BACKUP}: {'present' if os.path.exists(BACKUP) else 'missing'}")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--revert":
        sys.exit(do_revert())
    if arg == "--status":
        sys.exit(do_status())
    if arg not in ("", "--patch"):
        print(__doc__)
        sys.exit(2)
    sys.exit(do_patch())
