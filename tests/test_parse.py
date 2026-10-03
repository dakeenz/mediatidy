"""Parser checks with generic examples. Run: python tests/test_parse.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mediatidy.parse import parse_filename, clean_filename

# (input, expected clean name) — None means "left alone"
CASES = [
    ("Pulp.Fiction.1994.1080p.BluRay.x264.YIFY.mp4",
     "Pulp Fiction (1994).mp4"),
    ("The.Hangover.2009.1080p.BluRay.x264.mkv",
     "The Hangover (2009).mkv"),
    ("Terminator.2.1991.Extended.1080p.h264.mkv",
     "Terminator 2 (1991) - Extended.mkv"),
    ("Se7en.1995.XViD.REQUEST.avi", "Se7en (1995).avi"),
    ("Jaws.1975.1080p.WEBRip.DDP.5.1.x264.mkv", "Jaws (1975).mkv"),
    ("Dune.1984.Extended.1080p.H264.AC-3.mkv",
     "Dune (1984) - Extended.mkv"),
    ("Rocky.1976.mp4", "Rocky (1976).mp4"),
    ("Dune.Part.Two.2024.1080p.burnt.in.subtitles.mp4",
     "Dune Part Two (2024).mp4"),
    ("Napoleon.Dynamite.2004.1080p.BluRay.x264.mp4",
     "Napoleon Dynamite (2004).mp4"),
    ("The.Shining.1980.REMASTERED.DUAL.1080p.mkv",
     "The Shining (1980) - Remastered.mkv"),
    # release-group / codec junk must not leak into titles:
    ("Deadpool.and.Wolverine.2024.1080p.WEBRip.x264.AAC5.1-[YTS.MX].mp4",
     "Deadpool and Wolverine (2024).mp4"),
    ("Rocky.1976.1080p.WEBRip.DDP.5.1.H.265-EDGE2020.mkv",
     "Rocky (1976).mkv"),
    ("Hot.Fuzz.2007.1080p.WEBRip.HEVC.x265-Mkvking.mkv",
     "Hot Fuzz (2007).mkv"),
    ("Civil.War.2024.1080p.AMZN.WEBRip.1400MB.DD5.1.x264-GalaxyRG.mkv",
     "Civil War (2024).mkv"),
    ("Spider-Man.Into.the.Spider-Verse.2018.XviD.Dts-Prozac.avi",
     "Spider-Man Into the Spider-Verse (2018).avi"),
    ("The.Evil.Dead.[Bootleg.2].1981.DVDRip.XviD.CG.[GS].avi",
     "The Evil Dead (1981).avi"),
    ("Superbad.2007.1080p.BluRay.x265.Bandi.mkv",
     "Superbad (2007).mkv"),
    ("Parasite.2019.Extended.1080p.h264.Ac3.Ita.Ac3.5.1.Eng.Sub"
     ".Ita.Eng.Spa-MIRCrew.mkv",
     "Parasite (2019) - Extended.mkv"),
    # TV episodes:
    ("Stranger.Things.S01E01.1080p.WEB.H264-NHTFS.mkv",
     "Stranger Things S01E01.mkv"),
    ("Stranger.Things.S01E02.1080p.WEB.H264-NHTFS.mkv",
     "Stranger Things S01E02.mkv"),
    ("Breaking.Bad.S02E05.720p.HDTV.x264.mkv", "Breaking Bad S02E05.mkv"),
    ("The.Office.S01E01.1080p.WEB-DL.mkv", "The Office S01E01.mkv"),
    ("The.Mandalorian.2019.S01E01E02.1080p.BluRay.mkv",
     "The Mandalorian (2019) S01E01-E02.mkv"),
    ("The.Wire.1x03.HDTV.avi", "The Wire S01E03.avi"),
    ("The.Simpsons.S01.E01-E02.1080p.mp4",
     "The Simpsons S01E01-E02.mp4"),
    ("The.Simpsons.S01.E03.1080p.mp4", "The Simpsons S01E03.mp4"),
    ("Wheel.of.Fortune.-.101.-.Bonus.Round.HDTV.avi",
     "Wheel of Fortune S01E01.avi"),
    ("Wheel.of.Fortune.-.213.-.Final.Spin.HDTV.avi",
     "Wheel of Fortune S02E13.avi"),
    ("Wheel.of.Fortune.-.403-404.-.Best.Of.HDTV.avi",
     "Wheel of Fortune S04E03-E04.avi"),
    # left alone:
    ("73ID02FFYw20.mp4", None),
    ("rangmaster.mp4", None),
    ("No.Time.to.Die.BluRay.1080p.x264.5.1.Judas.mp4", None),  # no year
    ("Space.Jam.mp4", None),                                    # no year
]


def main() -> int:
    fails = 0
    print(f"{'BEFORE':55} -> AFTER")
    print("-" * 100)
    for raw, expected in CASES:
        p = parse_filename(raw)
        got = clean_filename(p) if p.recognized else None
        ok = (got == expected)
        mark = "ok " if ok else "FAIL"
        if not ok:
            fails += 1
        print(f"[{mark}] {raw:55} -> {got}")
        if not ok:
            print(f"       expected: {expected}   reason: {p.reason}")
    # clutter must be captured, not lost
    p = parse_filename("Pulp.Fiction.1994.1080p.BluRay.x264.YIFY.mp4")
    assert any("1080p" in c for c in p.claimed), p.claimed
    assert any("BluRay" in c for c in p.claimed), p.claimed
    assert any("x264" in c for c in p.claimed), p.claimed
    p = parse_filename("Dune.1984.Extended.1080p.H264.AC-3.mkv")
    assert p.edition == "Extended", p.edition
    assert any("AC-3" in c for c in p.claimed), p.claimed
    print(f"\n{len(CASES) - fails}/{len(CASES)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
