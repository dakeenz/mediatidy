"""Tests for parse_foldername: folder names get the same style as files."""
import sys
sys.path.insert(0, ".")

from mediatidy.parse import parse_foldername

CASES = [
    # (folder name, expected new name or None)
    ("The.Hangover.2009.1080p.BluRay.x264.AAC5.1-anonymous",
     "The Hangover (2009)"),
    ("Mad.Max.Fury.Road.2015.1080p.BluRay.x264-GalaxyRG",
     "Mad Max Fury Road (2015)"),
    ("The.Shining.1980.REMASTERED.1080p.BRRip.x264.AAC-ETRG",
     "The Shining (1980) - Remastered"),
    ("www.Example.com - The.Matrix.1999.1080p.BluRay.x264-OFT",
     "The Matrix (1999)"),
    ("The.Thing.1982.x264DVDrip(HorrorClassics)", "The Thing (1982)"),
    ("Dune.Part.Two.2024.UHD.4K.BluRay.2160p.DoVi.HDR10 "
     "TrueHD.7.1.Atmos.H.265-MgB", "Dune Part Two (2024)"),
    ("Superbad.2007.1080p.{5.1}.x264", "Superbad (2007)"),
    ("BREAKING.BAD[SEASONS.1-5][VERIFIED-VIDZ]", "Breaking Bad"),
    ("The Office (2005-2013) - Complete Series, S01-S09 - 1080p WEB-DL x264",
     "The Office (2005)"),
    ("The.Wire.TV.Series.Season.1.2002.XviD.576x432.88",
     "The Wire (2002)"),
    ("Looney Tunes Complete Collection HQ-DVD-Rip", "Looney Tunes"),
    ("The.Simpsons.Season.1.1080p.WEB-DL", "The Simpsons"),
    ("stranger.things.s1", "Stranger Things"),
    ("game.of.thrones", "Game of Thrones"),
    ("The.Dark.Knight.2008.1080p.BluRay.x264.[YTS]", "The Dark Knight (2008)"),
    # left alone
    ("HBO", None),
    ("S1", None),
    ("Subs", None),
    ("Season 1 (1999)", None),
    ("Season 2 (1999-2000)", None),
    ("Specials (2002-09)", None),
    ("1930", None),
    ("Pixar Shorts", None),
    ("Doctor Who at BBC", None),
    ("The Grand Budapest Hotel (2014)", None),
]


def main() -> int:
    fails = 0
    for name, expected in CASES:
        got, kind = parse_foldername(name)
        ok = got == expected
        print(f"[{'ok' if ok else 'FAIL'}] {name[:60]:62} -> {got}")
        if not ok:
            print(f"       expected: {expected} (kind={kind})")
            fails += 1
    print(f"\n{len(CASES) - fails}/{len(CASES)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
