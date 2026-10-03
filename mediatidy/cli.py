"""Command-line interface: scan, preview (dry-run), apply, undo."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .parse import VIDEO_EXTS
from .planner import build_plan, build_folder_plan
from .nfo import write_nfo
from . import enrich as enrich_mod


def _check_env() -> int:
    import platform
    import shutil
    print(f"Python: {platform.python_version()} "
          f"({platform.python_implementation()})")
    print(f"OS: {platform.system()} {platform.release()} "
          f"/ arch: {platform.machine()}")
    if shutil.which("ffprobe"):
        print("ffprobe: found (quality verification available)")
    else:
        print("ffprobe: not found (duplicates will be flagged unverified; "
              "install ffmpeg to enable)")
    return 0


def _program_dir() -> Path:
    """Directory holding the running program.

    The folder planner must never rename this directory or any of its
    parents: doing so would rename the program out from under itself
    while it is running (e.g. the user picks a folder that contains the
    extracted MediaTidy folder).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _self_protected_dirs() -> set[Path]:
    d = _program_dir()
    return {d, *d.parents}


def _iter_files(root: Path, recursive: bool):
    if recursive:
        gen = root.rglob("*")
    else:
        gen = root.iterdir()
    for p in sorted(gen):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            yield p


def _print_plan(entries, unrecognized, warnings, dry_run: bool):
    if dry_run:
        print("DRY RUN — no files changed. Re-run with --apply to perform.\n")
    if entries:
        width = max(len(e.src.name) for e in entries)
        print(f"RENAME ({len(entries)}):")
        for e in entries:
            flag = f"  [{e.note}]" if e.note else ""
            print(f"  {e.src.name:<{width}}  ->  {e.dest_name}{flag}")
        print()
    if unrecognized:
        print(f"UNRECOGNIZED ({len(unrecognized)}) — left alone:")
        for name, reason in unrecognized:
            print(f"  {name}  ({reason})")
        print()
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  ! {w}")
        print()


def _apply(entries, log_path: Path, enrich: bool = False,
           omdb_key: str | None = None, folder_entries=None):
    log = {"renames": [], "folder_renames": [], "nfos": []}
    api_key = enrich_mod.resolve_api_key(omdb_key) if enrich else None
    if enrich and not api_key:
        print("  ! --enrich needs an OMDb API key: pass --omdb-key, set "
              "OMDB_API_KEY, or save it to the mediatidy config file.\n"
              "    Continuing without enrichment.", file=sys.stderr)
    cache = enrich_mod.load_cache() if api_key else {}
    for e in entries:
        dest = e.src.parent / e.dest_name
        if dest != e.src:
            try:
                e.src.rename(dest)
            except OSError as exc:
                print(f"  ! rename failed, skipped: {e.src.name}: {exc}",
                      file=sys.stderr)
                continue
            log["renames"].append({"from": str(e.src), "to": str(dest)})
        else:
            dest = e.src  # already clean; still write tags
        # tags need the parsed title/year: recover from dest stem, which is
        # "Title (Year)" / "Title (Year) - Edition" for movies, or
        # "Title [(Year)] S01E01 [-E02]" for episodes
        title, year, season, episode = dest.stem, 0, None, None
        m = re.match(r"^(.*?)\s+\((\d{4})\)(?:\s+-\s+(.*))?$", dest.stem)
        if m:
            title, year = m.group(1), int(m.group(2))
        else:
            m2 = re.match(r"^(.*?)(?:\s+\((\d{4})\))?"
                          r"\s+[Ss](\d{1,2})[Ee](\d{1,3})(?:-[Ee](\d{1,3}))?$",
                          dest.stem)
            if m2:
                title = m2.group(1)
                year = int(m2.group(2)) if m2.group(2) else 0
                season, episode = int(m2.group(3)), int(m2.group(4))
        try:
            info = None
            if api_key:
                # enrichment never blocks the rename or the basic tags
                try:
                    if season is not None and episode is not None:
                        info = enrich_mod.enrich_episode(
                            title, season, episode, api_key, cache)
                    elif year:
                        info = enrich_mod.enrich_movie(
                            title, year, api_key, cache)
                except Exception as exc:
                    print(f"  ! enrichment failed for {dest.name}: {exc}",
                          file=sys.stderr)
            nfo = write_nfo(dest, title, year, e.tags,
                            season=season, episode=episode,
                            director=info.get("director") if info else None,
                            actors=info.get("actors") if info else None,
                            genres=info.get("genre") if info else None,
                            imdb_id=info.get("imdb_id") if info else None,
                            imdb_rating=info.get("imdb_rating")
                            if info else None)
            log["nfos"].append(str(nfo))
        except Exception as exc:  # never let tags block the rename
            print(f"  ! nfo failed for {dest.name}: {exc}", file=sys.stderr)
    if folder_entries:
        for fe in folder_entries:  # already deepest-first
            dest = fe.src.parent / fe.dest_name
            if dest == fe.src or dest.exists():
                continue
            try:
                fe.src.rename(dest)
            except OSError as exc:
                # usually a locked file inside (e.g. torrent client seeding):
                # warn and keep going so one folder can't kill the run
                print(f"  ! folder rename failed, skipped: {fe.src.name}: "
                      f"{exc}", file=sys.stderr)
                continue
            log["folder_renames"].append(
                {"from": str(fe.src), "to": str(dest)})
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"Done: {len(log['renames'])} renamed, "
          f"{len(log['nfos'])} .nfo written. Log: {log_path}")


def _map_through_renames(path: str, renames) -> Path:
    """Map a logged path to its current location after renames (deepest-first)."""
    import os
    s = path
    for r in renames:
        frm, to = r["from"], r["to"]
        if s == frm or s.startswith(frm + os.sep):
            s = to + s[len(frm):]
    return Path(s)


def _try_unlink(p: Path):
    try:
        p.unlink(missing_ok=True)
    except TypeError:  # Python < 3.8
        if p.exists():
            p.unlink()


def _undo(log_path: Path):
    if not log_path.exists():
        print(f"No log found at {log_path}", file=sys.stderr)
        sys.exit(1)
    log = json.loads(log_path.read_text(encoding="utf-8"))
    folder_renames = log.get("folder_renames", [])
    # .nfo files were written before folders were renamed: map their logged
    # paths through the folder renames to find where they are now
    for nfo in log.get("nfos", []):
        _try_unlink(_map_through_renames(nfo, folder_renames))
    # folders were renamed deepest-first: undo shallowest-first, before
    # files (a file's logged path is stale while its folder is renamed)
    for r in reversed(folder_renames):
        src, dst = Path(r["from"]), Path(r["to"])
        if dst.exists():
            dst.rename(src)
    for r in reversed(log.get("renames", [])):
        src, dst = Path(r["from"]), Path(r["to"])
        if dst.exists():
            dst.rename(src)
    total = len(log.get("renames", [])) + len(folder_renames)
    print(f"Undone: {total} renames reversed, "
          f"{len(log.get('nfos', []))} .nfo files removed.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="mediatidy",
        description="Clean up archived media filenames; verify quality; "
                    "write .nfo sidecar tags. Dry-run by default.")
    ap.add_argument("path", nargs="?", help="folder to scan")
    ap.add_argument("--check", action="store_true",
                    help="report whether this device can run mediatidy "
                         "(Python version, OS/arch, ffprobe)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="scan subfolders too")
    ap.add_argument("--probe", action="store_true",
                    help="verify real quality with ffprobe (needs ffmpeg) "
                         "when duplicate titles are found")
    ap.add_argument("--apply", action="store_true",
                    help="perform the renames (default is dry-run preview)")
    ap.add_argument("--undo", action="store_true",
                    help="reverse the last --apply using the log file")
    ap.add_argument("--log", default="mediatidy_log.json",
                    help="rename log for --apply/--undo "
                         "(default: mediatidy_log.json)")
    ap.add_argument("--enrich", action="store_true",
                    help="look up director/actors from IMDb data (via the "
                         "free OMDb API) and add them to each .nfo")
    ap.add_argument("--folders", action="store_true",
                    help="also rename folders in the same style "
                         "(whole tree, deepest first)")
    ap.add_argument("--omdb-key", default=None,
                    help="OMDb API key for --enrich (or set OMDB_API_KEY, "
                         "or save it to the mediatidy config file)")
    args = ap.parse_args(argv)

    if args.check:
        return _check_env()

    log_path = Path(args.log)
    if args.undo:
        _undo(log_path)
        return 0

    if not args.path:
        ap.error("path is required (unless using --check or --undo)")
    root = Path(args.path)
    if not root.is_dir():
        print(f"Not a folder: {root}", file=sys.stderr)
        return 2

    files = list(_iter_files(root, args.recursive))
    folder_entries, folder_unrec, folder_warnings = ([], [], [])
    if args.folders:
        folder_entries, folder_unrec, folder_warnings = \
            build_folder_plan(root)
        # never rename the folder holding this program (or its parents):
        # renaming it would move the running program out from under itself
        protected = _self_protected_dirs()
        kept = []
        for fe in folder_entries:
            if fe.src.resolve() in protected:
                folder_warnings.append(
                    f"skipped (holds the running program): {fe.src.name}")
            else:
                kept.append(fe)
        folder_entries = kept
    if not files and not folder_entries and not args.folders:
        print("No video files found.")
        return 0

    entries, unrecognized, warnings = ([], [], [])
    if files:
        entries, unrecognized, warnings = build_plan(files, probe=args.probe)
    _print_plan(entries, unrecognized, warnings, dry_run=not args.apply)
    if folder_entries or folder_unrec or folder_warnings:
        print("FOLDERS:")
        _print_plan(folder_entries, folder_unrec, folder_warnings,
                    dry_run=not args.apply)
    if args.apply:
        _apply(entries, log_path, enrich=args.enrich,
               omdb_key=args.omdb_key, folder_entries=folder_entries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
