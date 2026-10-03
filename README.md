# MediaTidy

Rename messy archived media files into clean, consistent names — and tag
them with open `.nfo` sidecars so nothing about the original file is lost.

## Download

No Python, no technical setup. Grab the Windows build from
[Releases](https://github.com/dakeenz/mediatidy/releases), unzip it, and
double-click `tidy-media.bat`. It asks which folder to tidy, shows what it
will rename, and asks before changing anything. Everything is undoable.

## The rule

- **Immediately recognizable titles** → `Title (Year).ext`, or
  `Title (Year) - Edition.ext` when there's an edition worth keeping
  (Extended, Remastered, Director's Cut…).
- **Anything not confidently recognizable** → left completely alone, listed
  for manual review. Never guessed.
- **Release clutter is stripped from names** (1080p, BluRay, x264, YIFY…)
  but **kept as tags** in the `.nfo` file.
- **Two versions of the same title** (e.g. a 1080p and a 4K copy): the
  real quality is probed from the file's metadata with `ffprobe` — the
  filename's claims are *not* trusted — and the verified quality goes in
  the name (`Title (Year) [1080p].mkv`) plus full detail in the tags.

## What's an .nfo sidecar?

A tiny open-standard XML file next to the video:

```
UHF (1989).mp4  →  UHF (1989).nfo
```

Kodi, Jellyfin and Emby all read them (title, year, tags). They're plain
text — nothing proprietary, readable forever. The AutoPlaylist
VLC extension reads `<genre>`, `<director>`, `<actor>` and `<title>` tags
from `.nfo` files, so tags written here flow into themed playlists.

## Usage

Dry-run first — always. Nothing is renamed until you say so:

```bash
# preview what would happen
python -m mediatidy "D:\Videos" --recursive

# same, but verify real quality for duplicate titles (needs ffmpeg)
python -m mediatidy "D:\Videos" --recursive --probe

# actually do it (writes mediatidy_log.json)
python -m mediatidy "D:\Videos" --recursive --probe --apply

# change your mind
python -m mediatidy "D:\Videos" --undo --log mediatidy_log.json
```

Every `--apply` writes a log, and `--undo` reverses renames and removes
the `.nfo` files it created.

### IMDb enrichment (optional)

IMDb publishes no public API, so enrichment goes through OMDb
(omdbapi.com), which serves IMDb's own data — director, actors, IMDb ID
and rating. It's a free key with 1,000 lookups/day:

```bash
# add director/actor/genre tags to every .nfo
python -m mediatidy "D:\Videos" --apply --enrich --omdb-key YOUR_KEY
```

The key can also come from the `OMDB_API_KEY` environment variable, or a
file containing just the key at `%APPDATA%\mediatidy\omdb.key`. Lookups are
cached locally, so re-running costs nothing. If the key is missing or the
network fails, you still get the normal rename and basic `.nfo` tags —
enrichment never blocks the run.

### Folder renaming (optional)

`--folders` renames folders in the same style, across the whole tree
(deepest first). Season folders, `Subs`/`Covers`, year folders and
single-acronym names are left alone:

```bash
python -m mediatidy "D:\Videos" --recursive --folders --apply
```

## Examples

| Before | After | Ability |
|---|---|---|
| `Pulp.Fiction.1994.1080p.BluRay.x264.YIFY.mp4` | `Pulp Fiction (1994).mp4` | strips quality/codec/group junk |
| `Dune.1984.Extended.1080p.H264.AC-3.mkv` | `Dune (1984) - Extended.mkv` | keeps real editions |
| `Deadpool.and.Wolverine.2024.1080p.WEBRip.x264.AAC5.1-[YTS.MX].mp4` | `Deadpool and Wolverine (2024).mp4` | bracketed release groups |
| `Parasite.2019.1080p.h264.Ac3.Ita.Ac3.5.1.Eng.Sub.Ita.Eng.Spa-MIRCrew.mkv` | `Parasite (2019).mkv` | multi-language clutter |
| `Se7en.1995.XViD.REQUEST.avi` | `Se7en (1995).avi` | numbers inside titles |
| `Stranger.Things.S01E01.1080p.WEB.H264-NHTFS.mkv` | `Stranger Things S01E01.mkv` | TV episodes |
| `The.Mandalorian.2019.S01E01E02.1080p.BluRay.mkv` | `The Mandalorian (2019) S01E01-E02.mkv` | multi-episode files |
| `The.Wire.1x03.HDTV.avi` | `The Wire S01E03.avi` | alternate episode formats |
| `The.Dark.Knight.2008.1080p.BluRay.x264.[YTS]` | `The Dark Knight (2008)` | folder renaming |
| `73ID02FFYw20.mp4` | *left alone* | never guesses |

TV episodes are recognized by `S01E01` / `1x01` markers (year optional);
each episode gets a Kodi-style `<episodedetails>` `.nfo` with season and
episode numbers.

## Requirements

- Python 3.9+ — no third-party packages, standard library only.
- Optional: `ffmpeg` (for `ffprobe`) to verify real quality on duplicates.

## Platform support

**Linux** — verified. Clone and run:

```bash
python3 -m mediatidy "/path/to/videos" --recursive
```

**Windows (x86 and ARM)** — install Python 3.9+ from python.org or the
Microsoft Store, then run the same command. For a double-clickable
build later, the project can be frozen with PyInstaller
(`pip install pyinstaller && pyinstaller --onefile -n mediatidy-win-arm64 mediatidy/cli.py`).

**Android** — via [Termux](https://termux.dev) (F-Droid or GitHub
releases; avoid the outdated Play Store build):

```bash
pkg install python ffmpeg      # ffmpeg is optional, enables --probe
termux-setup-storage           # grants access to shared storage
cd ~/mediatidy
python -m mediatidy /storage/emulated/0/Videos --recursive
```

Run `python -m mediatidy --check` on any device to confirm the
environment (Python version, OS/arch, ffprobe presence) before scanning.

## Roadmap

- Music (embedded tags), books, software.
- Title/year lookup for files with no year in the name.
- Restoring punctuation the scene names dropped (`Ocean's Eleven`).

## Companion: AutoPlaylist

A VLC extension that scans a folder and builds themed playlists
(Comedy, Horror, Sci-Fi…) from the `.nfo` tags MediaTidy writes —
matching on title, genre, director and actors. MIT licensed, in
`../vlc/auto_playlist.lua`.
