# ⚡ MUGEN Smart Roster Manager

A dynamic pre-launch roster tool for **MUGEN 1.1** that eliminates long load times by letting you hand-pick exactly which characters and stages get written into `select.def` before each session — then restores your original file when you're done.

---

## The Problem

MUGEN doesn't load characters on demand. At startup it parses `select.def` and prepares **every single character** referenced in it — sprites, animations, sounds, and state tables — even if you only plan to play two fights. With large rosters this can mean minutes of loading time every launch.

## The Solution

This tool acts as a pre-launch pipeline:

1. **Scan** your full `chars/` and `stages/` library once
2. **Pick** only the characters and stages you want for this session
3. **Save** named profiles (`quickplay`, `testing`, `bossrush`, etc.)
4. **Launch** — the tool writes a lean `select.def`, starts MUGEN, and **automatically restores your original** when MUGEN exits

No engine patching. No file juggling. Just faster MUGEN.

---

## Features

- **Portrait preview** — hover over any character to see their `9000,1` VS portrait rendered live, bottom-anchored in a 120×140 display box with name and author shown alongside
- **Full character library** — scans your entire `chars/` folder recursively, reads each `.def` file to extract name, display name, and author
- **Group filtering** — automatically organises characters by their top-level subfolder (e.g. `chars/HYZEN/`, `chars/KOF/`)
- **Search** — filter characters and stages by name in real time
- **Named profiles** — save unlimited rosters as JSON files; switch between them instantly
- **Stage management** — select individual stages to include in `[ExtraStages]`
- **Auto backup & restore** — your original `select.def` is timestamped and backed up to `data/roster_backups/` before every launch, and restored automatically on exit
- **Apply Only** — write `select.def` without launching MUGEN, for manual testing
- **Scan cache** — your library is cached after the first scan so subsequent launches are instant
- **Python 3.7–3.13+ compatible** — built with zero broken CPython internals

---

## Screenshots

> *(Add your own screenshots here)*

```
┌─────────────────────────────────────────────────────────────────┐
│  CHARACTER INFO     │  CHARACTER LIBRARY          │  STAGES     │
│  ┌───────────────┐  │  Search...    Group: All ▾  │  Search...  │
│  │               │  │  ✓ Ryu                      │  ✓ KOF97…  │
│  │  [portrait]   │  │    Ken                      │    Altar    │
│  │               │  │  ✓ Kyo-8                    │  ✓ NESTS… │
│  └───────────────┘  │    Iori                     │             │
│  Kyo Kusanagi        │    Granheid                 │             │
│  by Sandstorm        │  ✓ Orochi                   │             │
│  ─────────────────  │                             │             │
│  PROFILES            │                             │             │
│  > quickplay         │                             │             │
│    testing           │                             │             │
│    bossrush          │                             │             │
│  [+ New] [💾 Save]  │  3 characters selected      │  2 selected │
├─────────────────────────────────────────────────────────────────┤
│  [ 💾 Apply Only ]                   [ ▶  LAUNCH MUGEN ]       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Requirements

- **MUGEN 1.1** (SFF v1 and v2 both supported for portrait reading)
- **Python 3.7+** — [python.org](https://www.python.org/downloads/) — check *"Add Python to PATH"* during install
- **Pillow** — for portrait rendering

```
pip install pillow
```

That's it. `tkinter` is included with standard Python on Windows.

---

## Installation

1. Download and extract the zip anywhere on your machine — it does **not** need to be inside your MUGEN folder
2. Install Pillow: `pip install pillow`
3. Run: `python launcher.py`
4. On first launch, click **⚙ Settings** and point it at your MUGEN root folder (e.g. `C:\mugen`)
5. The app will scan your `chars/` and `stages/` automatically

---

## Project Structure

```
mugen-roster-manager/
├── launcher.py              ← Main GUI app — run this
├── debug_portrait.py        ← Diagnostic tool for portrait issues
├── core/
│   ├── scanner.py           ← Scans chars/ and stages/, builds library
│   ├── sff_reader.py        ← Custom SFF v1/v2 parser, extracts 9000,1
│   ├── roster.py            ← Profile save/load (JSON)
│   ├── select_writer.py     ← Generates select.def + backup system
│   ├── mugen_runner.py      ← Backup → write → launch → restore pipeline
│   └── config_manager.py    ← App settings (paths, preferences)
├── libmugen/
│   ├── parse.py             ← MUGEN-native .def parser (Python 3.13 compatible)
│   └── config.py            ← guess_kind() — identifies characters vs stages
├── profiles/                ← Your saved rosters live here (auto-created)
├── requirements.txt
└── README.md
```

---

## How Profiles Work

Profiles are plain JSON files in the `profiles/` folder:

```json
{
  "name": "quickplay",
  "description": "",
  "characters": [
    "Kyo-8/Kyo-8.def",
    "Iori-CKOFM/Iori-CKOFM.def",
    "Orochi/orochi_release-ver.def"
  ],
  "stages": [
    "stages/KOF97-EmptyAltar.def",
    "stages/MUGEN-Moonlight.def"
  ]
}
```

You can edit these by hand if needed. Paths are relative to your `chars/` or `stages/` directory.

---

## How `select.def` Generation Works

The tool writes a minimal MUGEN 1.1 `select.def` containing only your selected characters:

```ini
; MUGEN Smart Roster Manager - Auto-generated select.def
; Profile: quickplay  |  Characters: 3  |  Stages: 2

[Characters]
Kyo-8/Kyo-8.def, order=1
Iori-CKOFM/Iori-CKOFM.def, order=1
Orochi/orochi_release-ver.def, order=1

[ExtraStages]
stages/KOF97-EmptyAltar.def
stages/MUGEN-Moonlight.def
```

Your original `select.def` is always backed up first to `data/roster_backups/select_YYYYMMDD_HHMMSS.def` and restored after MUGEN exits.

---

## Portrait Display

When you hover over a character in the library, the tool:

1. Reads the character's `.def` file to find the `sprite =` path in `[Files]`
2. Opens the `.sff` file and detects its version (SFF v1 or v2)
3. Walks the sprite table to find group `9000`, index `1` (the VS portrait)
4. Decodes the pixel data (supports PCX/RLE8/RLE5/LZ5/PNG formats)
5. Scales the image to fit 120×140 with **bottom anchoring** — characters always stand on the floor line

All loading happens on a background thread. Results are cached per session so each portrait only loads once.

---

## Folder Organisation Tips

The group filter works off your top-level subfolder names inside `chars/`. Organising like this gives you clean groups in the UI:

```
chars/
├── Street Fighter/
│   ├── ryu/
│   └── ken/
├── KOF/
│   ├── kyo-8/
│   └── iori-CKOFM/
├── Bosses/
│   └── orochi/
└── Testing/
    └── wip-char/
```

---

## Troubleshooting

**Characters not appearing after scan**
- Make sure each character folder has a `.def` file with an `[Info]` section containing `name =`
- Check `roster_manager.log` for parse warnings

**Stages show 0 after scan**
- Hit **🔄 Rescan** — the first version had a case-sensitivity bug in stage detection that is now fixed
- Delete `char_stage_cache.json` to force a fresh scan

**Portraits showing `?`**
- Run the diagnostic: `python debug_portrait.py "C:\path\to\chars"`
- Check `roster_manager.log` — all SFF reader steps are logged at INFO level

**MUGEN won't launch**
- Verify MUGEN root path in **⚙ Settings**
- Check that `mugen.exe` name matches exactly (some builds use `winmugen.exe`)

**`select.def` not restored after crash**
- Backups are always in `data/roster_backups/` — copy the most recent one back manually

---

## Technical Notes

### SFF v1 Subfile Header (32 bytes)
```
next_subfile   4  uint32   offset of next sprite in chain
length         4  uint32   total byte length including this header
axisx          2  uint16
axisy          2  uint16
groupno        2  uint16
imageno        2  uint16
index          2  uint16
palette_flag   1  uint8    1 = owns palette, 0 = uses shared
padding       13  bytes
```

### SFF v2 Sprite Entry (28 bytes)
```
groupno        2  uint16
itemno         2  uint16
width          2  uint16
height         2  uint16
axisx          2  uint16
axisy          2  uint16
index          2  uint16
format         1  uint8    0=raw 2=RLE8 3=RLE5 4=LZ5 10=PNG
colordepth     1  uint8
data_offset    4  uint32
data_length    4  uint32
palette_index  2  uint16
flags          2  uint16   bit0: 0=ldata 1=tdata
```

---

## Based On

Built on top of [mugen-tools](https://github.com/bitcraft/mugen-tools) by leif theden — specifically the `.def` file parsing infrastructure. The `MugenParser` was rewritten from scratch for Python 3.12/3.13 compatibility (the original relied on private `configparser` internals that were renamed in newer Python versions).

---

## License

MIT — do whatever you want with it.

---

*Built for MUGEN authors who have too many characters and not enough patience.*
