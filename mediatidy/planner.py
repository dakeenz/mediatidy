"""Build the rename plan: clean names, duplicate handling, unrecognized list."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .parse import parse_filename, clean_filename, VIDEO_EXTS
from . import metadata as meta


@dataclass
class PlanEntry:
    src: Path
    dest_name: str
    tags: list[str] = field(default_factory=list)
    note: str = ""


def _tags_for(parsed, info: dict | None) -> list[str]:
    tags: list[str] = []
    if parsed.edition:
        tags.append(f"Edition: {parsed.edition}")
    if parsed.claimed:
        tags.append("Source claimed: " + ", ".join(parsed.claimed))
    if info is not None:
        tags.append("Verified: " + meta.describe(info))
    tags.append(f"Original filename: {parsed.original}")
    return tags


def _with_suffix(clean: str, ext: str, suffix: str) -> str:
    low = clean.lower()
    assert low.endswith(ext.lower()), (clean, ext)
    return clean[:len(clean) - len(ext)] + suffix + clean[len(clean) - len(ext):]


def build_plan(files: list[Path], probe: bool = False):
    """Return (entries, unrecognized, warnings).

    entries: PlanEntry list for recognized files.
    unrecognized: [(filename, reason)] — left alone.
    warnings: [str] — things needing attention.
    """
    entries: list[PlanEntry] = []
    unrecognized: list[tuple[str, str]] = []
    warnings: list[str] = []

    parsed = []
    for f in files:
        if f.suffix.lower() not in VIDEO_EXTS:
            continue
        p = parse_filename(f.name)
        if not p.recognized:
            unrecognized.append((f.name, p.reason))
        else:
            parsed.append((f, p))

    groups: dict[tuple, list] = defaultdict(list)
    for f, p in parsed:
        # episodes: same show groups by season/episode, so S01E01 and S01E02
        # are not mistaken for duplicate copies of one file
        groups[(p.title.casefold(), p.year, p.season,
                p.episode, p.episode_end)].append((f, p))

    for (title_key, year, _season, _ep, _ep2), items in sorted(groups.items()):
        if len(items) == 1:
            f, p = items[0]
            dest = clean_filename(p)
            note = ""
            if dest == f.name:
                note = "already clean"
            entries.append(PlanEntry(f, dest, _tags_for(p, None), note))
            continue

        # Same title+year more than once: the separation may be relevant.
        # Verify real quality from metadata instead of trusting filenames.
        infos = []
        for f, p in items:
            info = meta.probe_media(str(f)) if probe else {"verified": False}
            infos.append((f, p, info))

        heights = {i["height"] for _, _, i in infos if i.get("height")}
        if len(heights) > 1:
            for f, p, info in infos:
                h = info.get("height")
                suffix = f" [{h}p]" if h else " [alt]"
                dest = _with_suffix(clean_filename(p), p.extension, suffix)
                tags = _tags_for(p, info)
                tags.append(f"Disambiguated by verified resolution: {h}p")
                entries.append(PlanEntry(
                    f, dest, tags,
                    note="duplicate title — separated by verified quality"))
        else:
            if probe and heights:
                note = "duplicate title, same verified quality"
            else:
                note = ("duplicate title — quality unverified "
                        "(re-run with --probe and ffmpeg installed)")
                warnings.append(
                    f"{title_key} ({year if year else 'no year'}): {len(items)} copies, "
                    "could not verify which is which")
            for n, (f, p, info) in enumerate(infos, 1):
                dest = clean_filename(p) if n == 1 else _with_suffix(
                    clean_filename(p), p.extension, f" ({n})")
                entries.append(PlanEntry(f, dest, _tags_for(p, info), note=note))

    # avoid clobbering files that already exist on disk
    seen: dict[str, Path] = {}
    for e in entries:
        target = e.src.parent / e.dest_name
        if (target.exists() and target.resolve() != e.src.resolve()
                and e.dest_name not in seen):
            warnings.append(f"name collision on disk: {e.dest_name}")
            base = e.dest_name
            n = 2
            while (e.src.parent / base).exists():
                stem, dot, ext = e.dest_name.rpartition(".")
                base = f"{stem} ({n}).{ext}"
                n += 1
            e.dest_name = base
            e.note += " (collision avoided)" if e.note else "collision avoided"
        seen[e.dest_name] = e.src

    return entries, unrecognized, warnings


@dataclass
class FolderEntry:
    src: Path
    dest_name: str
    note: str = ""


def build_folder_plan(root: Path):
    """Return (entries, unrecognized, warnings) for folder renames.

    Every directory under root is considered. Entries are ordered
    deepest-first so renames never invalidate a path still to process.
    """
    from .parse import parse_foldername

    entries: list[FolderEntry] = []
    unrecognized: list[tuple[str, str]] = []
    warnings: list[str] = []

    dirs = sorted(
        (p for p in root.rglob("*") if p.is_dir()),
        key=lambda p: (-len(p.parts), str(p)),
    )
    seen: set[tuple[str, str]] = set()  # (parent path, lower new name)
    for d in dirs:
        new, kind = parse_foldername(d.name)
        if new is None:
            if kind != "already clean":
                unrecognized.append((d.name, kind))
            continue
        key = (str(d.parent).lower(), new.lower())
        target = d.parent / new
        if key in seen or (target.exists()
                           and target.resolve() != d.resolve()):
            warnings.append(f"folder name collision, skipped: {d.name}")
            continue
        seen.add(key)
        entries.append(FolderEntry(d, new))

    return entries, unrecognized, warnings
