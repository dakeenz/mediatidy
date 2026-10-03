"""Enrichment checks with a stubbed OMDb API. Run: python tests/test_enrich.py"""
import io
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mediatidy import enrich as E
from mediatidy import nfo as N

CALLS = []

MOVIE_RESP = {
    "Title": "UHF", "Year": "1989", "Director": "Jay Levey",
    "Actors": "Weird Al Yankovic, David Bowe, Fran Drescher",
    "imdbID": "tt0098546", "imdbRating": "6.9", "Response": "True",
}
EP_RESP = {
    "Title": "Pilot", "Year": "2025", "Director": "John Doe",
    "Actors": "Jane Smith, Bob Jones",
    "imdbID": "tt1234567", "imdbRating": "8.1", "Response": "True",
}
NA_RESP = {
    "Title": "X", "Year": "2000", "Director": "N/A", "Actors": "N/A",
    "imdbID": "tt0000000", "imdbRating": "N/A", "Response": "True",
}
MISS_RESP = {"Response": "False", "Error": "Movie not found!"}


class FakeResp:
    def __init__(self, payload):
        self._buf = io.BytesIO(json.dumps(payload).encode())

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(url, timeout=None):
    CALLS.append(url)
    if "Episode=1" in url:
        return FakeResp(EP_RESP)
    if "t=Missing" in url:
        return FakeResp(MISS_RESP)
    if "t=Plain" in url:
        return FakeResp(NA_RESP)
    return FakeResp(MOVIE_RESP)


def main() -> int:
    urllib.request.urlopen = fake_urlopen
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(f"[{'ok ' if cond else 'FAIL'}] {name} {extra}")
        if not cond:
            fails += 1

    cache = {}
    m = E.enrich_movie("UHF", 1989, "KEY", cache)
    check("movie director", m["director"] == "Jay Levey", m)
    check("movie actors", m["actors"] == ["Weird Al Yankovic", "David Bowe",
                                         "Fran Drescher"], m["actors"])
    check("movie imdb id", m["imdb_id"] == "tt0098546")
    check("movie rating", m["imdb_rating"] == "6.9")

    n_calls = len(CALLS)
    m2 = E.enrich_movie("UHF", 1989, "KEY", cache)
    check("cache hit avoids network", m2 == m and len(CALLS) == n_calls)

    ep = E.enrich_episode("The Office", 1, 1, "KEY", cache)
    check("episode director", ep["director"] == "John Doe")
    check("episode actors", ep["actors"] == ["Jane Smith", "Bob Jones"])

    na = E.enrich_movie("Plain", 2000, "KEY", cache)
    check("N/A director -> None", na["director"] is None)
    check("N/A actors -> []", na["actors"] == [])

    miss = E.enrich_movie("Missing", 2000, "KEY", cache)
    check("not found -> None", miss is None)

    def boom(url, timeout=None):
        raise OSError("no network")

    urllib.request.urlopen = boom
    down = E.enrich_movie("UHF", 1990, "KEY", {})
    check("network failure -> None", down is None)

    # key resolution: env var
    import os
    os.environ["OMDB_API_KEY"] = "ENVKEY"
    check("env key", E.resolve_api_key() == "ENVKEY")
    check("cli key wins", E.resolve_api_key("CLI") == "CLI")
    del os.environ["OMDB_API_KEY"]
    check("no key -> None", E.resolve_api_key() is None)

    # nfo carries the enrichment
    xml = N.build_movie_nfo("UHF", 1989, ["Comedy"], director="Jay Levey",
                            actors=["Weird Al Yankovic"],
                            imdb_id="tt0098546", imdb_rating="6.9")
    check("nfo director", "<director>Jay Levey</director>" in xml)
    check("nfo actor", "<name>Weird Al Yankovic</name>" in xml)
    check("nfo imdbid", "<imdbid>tt0098546</imdbid>" in xml)
    check("nfo keeps genre tags", "<genre>Comedy</genre>" in xml)
    xml2 = N.build_episode_nfo("The Office", 1, 1, 2025, ["Comedy"],
                               director="John Doe")
    check("episode nfo director", "<director>John Doe</director>" in xml2)

    print(f"\n{15 - fails}/15 passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
