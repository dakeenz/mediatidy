"""Parse messy scene/release filenames into clean components.

Scope: movies where we can confidently find a title + year, and TV
episodes with a recognizable show name + SxxEyy marker (year optional).
Anything we can't confidently parse is reported as unrecognized and
left alone — never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

VIDEO_EXTS = frozenset({
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".ts", ".m2ts", ".mpg", ".mpeg",
})

EDITION_WORDS = [
    "extended",
    "remastered",
    "unrated",
    "director's cut",
    "directors cut",
    "theatrical cut",
    "special edition",
    "ultimate edition",
    "anniversary edition",
    "restored",
    "criterion",
]

# (regex, label) — matched tokens are stripped from the name and kept as
# "claimed" info so nothing is lost; they end up in the .nfo tags.
_CLUTTER_SRC = [
    (r"\b\d{3,4}p\b", "resolution"),
    (r"\b[48]k\b", "resolution"),
    (r"\buhd\b", "resolution"),
    (r"\bblu[\s\-]?ray\b", "source"),
    (r"\bweb[\s\-]?dl\b", "source"),
    (r"\bwebrip\b", "source"),
    (r"\bbrrip\b", "source"),
    (r"\bbdrip\b", "source"),
    (r"\bbrip\b", "source"),
    (r"\bdvdrip\b", "source"),
    (r"\bx264dvdrip\b", "source"),
    (r"\bx265dvdrip\b", "source"),
    (r"\bdvdscr\b", "source"),
    (r"\bhdtv\b", "source"),
    (r"\bpdtv\b", "source"),
    (r"\bamzn\b", "source"),
    (r"\bx26[45]\b", "video codec"),
    (r"\bh26[45]\b", "video codec"),
    (r"\bh[\s.\-]?26[45]\b", "video codec"),  # "H.265" -> "H 265" after cleanup
    (r"\bhevc\b", "video codec"),
    (r"\bxvid\b", "video codec"),
    (r"\bdivx\b", "video codec"),
    (r"\bav1\b", "video codec"),
    (r"\bvp9\b", "video codec"),
    (r"\b10bit\b", "video codec"),
    (r"\bddp\b", "audio"),
    (r"\bac[\s\-]?3\b", "audio"),
    (r"\bdts[\s\-]?hd\b", "audio"),
    (r"\bdts\b", "audio"),
    (r"\btruehd\b", "audio"),
    (r"\baac\b", "audio"),
    (r"\bflac\b", "audio"),
    (r"\bopus\b", "audio"),
    (r"\batmos\b", "audio"),
    (r"\b[578]\.1\b", "audio"),  # 5.1, 7.1 channel counts
    (r"\bdovi\b", "hdr"),
    (r"\bhdr10\+?\b", "hdr"),
    (r"\bhdr\b", "hdr"),
    (r"\b[a-z]*[257]_[01]\b", "audio"),  # 5_1, 2_0, AAC5_1, DD2_0 ...
    (r"\bdual\b", "audio"),
    (r"\bburnt in subtitles\b", "subtitles"),
    (r"\bsubtitles\b", "subtitles"),
    (r"\bsubs?\b", "subtitles"),
    (r"\b\d{3,4}x\d{3,4}\b", "resolution"),  # 576x432, 1920x1080
    (r"\bdoc\s+vostfr\b", "language"),
    (r"\bvostfr\b", "language"),
    (r"\b(ita|eng|spa|fre|ger|deu|jpn|kor|chi|dut|rus|por|ara|hin|"
    r"swe|nor|dan|fin|pol|ces|hun|tur)\b", "language"),
    (r"\b\d+(?:\.\d+)?\s?[kmg]b\b", "size"),  # 1400MB, 2.5GB ...
    (r"\brequest\b", "misc"),
]
_CLAIMED = [(re.compile(pat, re.I), label) for pat, label in _CLUTTER_SRC]

KNOWN_GROUPS = {
    "yify", "yts", "judas", "rarbg", "ettv", "evo", "tigole",
    "cytsun", "geckos", "amiable", "qxr", "mkvcage", "mkvking",
    "galaxyrg", "prozac", "edge2020", "bone", "eztv", "lol",
    "dimension", "tnt", "ntb", "deflate", "cg", "orenji",
    "bandi", "mircrew", "rbg", "oft", "tgx", "publichd", "hdb",
    "horrorclassics", "isa", "nikt0", "kingdom", "ozlem", "vppv",
    "lama", "lam", "etrg", "mgb", "genemige", "frys", "taoe", "vidz",
    "anonymous", "rekd", "handjob",
}

SMALL_WORDS = {
    "a", "an", "the", "and", "or", "of", "vs", "in",
    "on", "at", "to", "for", "with", "n", "'n'",
}

YEAR_RE = re.compile(r"\b(19\d{2}|20[0-2]\d)\b")

# TV episode markers: S01E01 / s1e1 (with optional E02 second episode),
# or 1x01 style. Spaces are tolerated: "S01 E01", "S01 E01-E02".
EP_RE = re.compile(r"\b[Ss](\d{1,2})\s*[Ee](\d{1,3})"
                   r"(?:\s*-?\s*[Ee](\d{1,3}))?\b")
EPX_RE = re.compile(r"\b(\d{1,2})[xX](\d{1,3})\b")
# "Show - 101 - Episode Title": 3-digit season+episode sandwich,
# with optional range ("Show - 403-404 - Title").
EP3_RE = re.compile(r"^(.*?)\s+-\s+(\d)(\d{2})"
                    r"(?:\s*-\s*(\d)(\d{2}))?(?:\s+-\s+|\s*$)")


@dataclass
class ParsedName:
    original: str
    title: str | None
    year: int | None
    edition: str | None
    extension: str
    recognized: bool
    claimed: list = field(default_factory=list)  # e.g. ["1080p (resolution)"]
    reason: str = ""
    kind: str = "movie"  # or "episode"
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None  # for S01E01E02 multi-episode files


def _find_editions(s: str) -> list[str]:
    found: list[str] = []
    seen = set()
    for w in EDITION_WORDS:
        if re.search(r"\b" + re.escape(w) + r"\b", s, re.I):
            key = w.replace("'", "").lower()
            if key in seen:
                continue
            seen.add(key)
            # "director's cut" and "directors cut" are the same edition
            if key == "directors cut" and "directors cut" in seen:
                continue
            found.append(" ".join(p.capitalize() for p in w.split()))
    # collapse the director's cut variants
    out, seen2 = [], set()
    for e in found:
        k = e.replace("'", "").lower()
        if k not in seen2:
            seen2.add(k)
            out.append(e.replace("Directors Cut", "Director's Cut"))
    return out


def _strip_editions(s: str) -> str:
    for w in EDITION_WORDS:
        s = re.sub(r"\b" + re.escape(w) + r"\b", " ", s, flags=re.I)
    return s


def _strip_groups(s: str, aggressive: bool = True) -> str:
    for g in KNOWN_GROUPS:
        s = re.sub(r"\b" + re.escape(g) + r"\b", " ", s, flags=re.I)
    if not aggressive:
        return s
    # a trailing ALL-CAPS token is usually the release group — but only
    # strip it when other words remain (so "UHF" survives).
    tokens = s.split()
    if len(tokens) > 1 and re.fullmatch(r"[A-Z0-9]{2,}", tokens[-1]):
        tokens = tokens[:-1]
    return " ".join(tokens)


def _strip_bracketed(s: str) -> str:
    """Drop [...] and {...} segments: scene names use them for release-group and
    info junk (e.g. [YTS.MX], [GS], {5.1}), never for the real title."""
    return re.sub(r"\[[^\[\]]*\]|\{[^{}]*\}", " ", s)


def _strip_parens(s: str) -> str:
    """Drop ( ... ) segments that don't hold the year: scene names put
    codec/group junk in parens, e.g. "(1080p BluRay x265 Bandi)"."""
    return re.sub(r"\((?![^()]*\b(?:19\d{2}|20[0-2]\d)\b)[^()]*\)", " ", s)


def _looks_like_hash(token: str) -> bool:
    if len(token) < 8:
        return False
    has_digit = any(c.isdigit() for c in token)
    has_upper = any(c.isupper() for c in token)
    has_lower = any(c.islower() for c in token)
    return has_digit and (has_upper and has_lower or len(token) >= 12)


def smart_title(s: str) -> str:
    words = s.split()
    out = []
    for i, w in enumerate(words):
        if re.fullmatch(r"[A-Z0-9]{2,}", w):
            out.append(w)  # acronyms like UHF stay as-is
            continue
        low = w.lower()
        if i != 0 and low in SMALL_WORDS:
            out.append(low)
            continue
        parts = re.split(r"(-)", w)
        out.append("".join(
            p[:1].upper() + p[1:].lower() if p != "-" else p
            for p in parts if p
        ))
    return " ".join(out)


def parse_filename(filename: str) -> ParsedName:
    base, dot, ext = filename.rpartition(".")
    if not dot:
        return ParsedName(filename, None, None, None, "", False,
                          reason="no extension")
    extension = "." + ext
    s = base.replace(".", " ").replace("_", " ")
    # protect 5.1/2.0-style audio notation (now space-separated); glue a
    # codec prefix on first ("AAC5.1" -> "AAC5 1" -> "AAC5_1") so the whole
    # token is claimed as audio instead of leaking into the title
    s = re.sub(r"\b([A-Z]{2,})([257]) ([01])\b", r"\1\2_\3", s)
    s = re.sub(r"\b([257]) ([01])\b", r"\1_\2", s)
    s = re.sub(r"\s+", " ", s).strip()

    # TV episode? Detect before anything else strips the marker.
    season = episode = episode_end = None
    ep_match = EP_RE.search(s) or EPX_RE.search(s) or EP3_RE.search(s)
    is_episode = ep_match is not None
    show_src = None
    if is_episode:
        groups = ep_match.groups()
        if ep_match.re is EP3_RE:
            show_src = groups[0]
            season, episode = int(groups[1]), int(groups[2])
            if len(groups) > 4 and groups[4]:
                episode_end = int(groups[4])
        else:
            season, episode = int(groups[0]), int(groups[1])
            if len(groups) > 2 and groups[2]:
                episode_end = int(groups[2])
            # the show name lives before the marker; everything after it is
            # release clutter that must not leak into the title
            show_src = s[:ep_match.start()]
        s = show_src + " " + s[ep_match.end():]
        s = re.sub(r"\s+", " ", s).strip()

    m = YEAR_RE.search(s)
    year = int(m.group(1)) if m else None

    editions = _find_editions(s)
    edition = " / ".join(editions) if editions else None
    s = _strip_editions(s)
    s = _strip_bracketed(s)
    s = _strip_parens(s)

    claimed: list[str] = []
    for rx, label in _CLAIMED:
        for tok in rx.findall(s):
            claimed.append(f"{tok.strip()} ({label})")
        s = rx.sub(" ", s)

    s = _strip_groups(s)
    if year is not None:
        s = YEAR_RE.sub(" ", s, count=1)
    s = re.sub(r"[\[\](){}]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -")

    title = smart_title(s) if s else None
    if is_episode:
        # title comes from the pre-marker text only, cleaned the same way
        t = show_src
        t = _strip_editions(t)
        t = _strip_bracketed(t)
        t = _strip_parens(t)
        if year is not None:
            t = YEAR_RE.sub(" ", t, count=1)
        t = _strip_groups(t)
        t = re.sub(r"[\[\](){}]", " ", t)
        t = re.sub(r"\s+", " ", t).strip(" -")
        title = smart_title(t) if t else None

    if is_episode:
        recognized, reason = True, ""
        if not title:
            recognized, reason = False, "no show name left after cleaning"
        elif len(title.split()) == 1 and _looks_like_hash(title):
            recognized, reason = False, "show name looks like a hash/ID"
    else:
        recognized, reason = True, ""
        if year is None:
            recognized, reason = False, "no year found"
        elif not title:
            recognized, reason = False, "no title left after cleaning"
        elif len(title.split()) == 1 and _looks_like_hash(title):
            recognized, reason = False, "title looks like a hash/ID"

    return ParsedName(
        original=filename,
        title=title if recognized else None,
        year=year if recognized else None,
        edition=edition if recognized else None,
        extension=extension,
        recognized=recognized,
        claimed=claimed,
        reason=reason,
        kind="episode" if is_episode and recognized else "movie",
        season=season if recognized else None,
        episode=episode if recognized else None,
        episode_end=episode_end if recognized else None,
    )


def clean_filename(p: ParsedName) -> str:
    """Build the target filename.

    Movies: Title (Year) [- Edition].ext
    Episodes: Title [(Year)] S01E01 [-E02].ext
    """
    if p.kind == "episode":
        base = p.title
        if p.year:
            base += f" ({p.year})"
        ep = f"S{p.season:02d}E{p.episode:02d}"
        if p.episode_end:
            ep += f"-E{p.episode_end:02d}"
        return f"{base} {ep}{p.extension.lower()}"
    base = f"{p.title} ({p.year})"
    if p.edition:
        base += f" - {p.edition}"
    return base + p.extension.lower()


def _strip_www_prefix(s: str) -> str:
    """Drop leading 'www.site.com - ' junk some folders carry."""
    return re.sub(r"^www\.\S+\s*-\s*", "", s, flags=re.I)


def _looks_like_show_pack(s: str) -> bool:
    low = s.lower()
    return ("complete" in low or "seasons" in low or "tv series" in low
            or "season" in low
            or re.search(r"s\d+\s*-\s*s\d+", low) is not None)


# acronyms worth keeping uppercase in show-folder names
_SHOW_ACRONYMS = {
    "mgm", "mde", "mxc", "tv", "hbo", "amc", "bbc", "nbc", "abc", "cbs",
    "pbs", "tnt", "fx", "usa", "dc",
}


def parse_foldername(name: str) -> tuple[str | None, str]:
    """Clean a folder name in the same style as files.

    Returns (new_name, kind) where new_name is None when the folder
    should be left alone. kind is "movie", "show", or a leave-alone reason.
    """
    s = _strip_www_prefix(name)

    # season/specials subfolders are organization, not titles — never touch
    if re.match(r"(?i)^(season|specials)\b", s):
        return None, "left alone"

    if not _looks_like_show_pack(s):
        p = parse_filename(s + ".mkv")
        if p.recognized and p.kind == "movie":
            new = f"{p.title} ({p.year})"
            if p.edition:
                new += f" - {p.edition}"
            return (None, "already clean") if new == name else (new, "movie")

    # Show-style cleaning: strip pack junk and title-case what's left.
    t = re.split(r"(?:\s*-\s*complete\b|\s+complete\s+collection\b)",
                 s, flags=re.I)[0]
    t = t.replace(".", " ").replace("_", " ")
    t = re.sub(r"\s+", " ", t).strip()
    year = None
    m = re.search(r"\((19\d{2}|20[0-2]\d)\s*-\s*\d{2,4}\)", t)
    if m:
        year = int(m.group(1))
        t = t.replace(m.group(0), " ", 1)
    else:
        m = YEAR_RE.search(t)
        if m:
            year = int(m.group(1))
            t = YEAR_RE.sub(" ", t, count=1)
    t = _strip_bracketed(t)
    t = _strip_parens(t)
    for rx, label in _CLAIMED:
        t = rx.sub(" ", t)
    t = _strip_groups(t, aggressive=False)
    t = re.sub(r"\btv\s+series\b", " ", t, flags=re.I)
    t = re.sub(r"\bseason\s+\d{1,2}\b", " ", t, flags=re.I)
    t = re.sub(r"\s+s\d{1,2}$", "", t, flags=re.I)
    t = re.sub(r"\s+\d{2}$", "", t)  # trailing disc/junk number
    t = re.sub(r"[\[\](){}]", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -")
    if not t:
        return None, "left alone"
    if re.fullmatch(r"[A-Z0-9]{2,}", t):
        return None, "left alone"  # single acronym (MXC, EXTRAS) — keep
    title = smart_title(t.lower())
    # restore known acronyms the lowercasing flattened (MGM, MDE, ...)
    words = []
    for w in title.split(" "):
        words.append(w.upper() if w.lower() in _SHOW_ACRONYMS else w)
    title = " ".join(words)
    if year:
        title += f" ({year})"
    return (None, "already clean") if title == name else (title, "show")
