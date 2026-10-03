"""Optional IMDb-sourced enrichment for .nfo sidecars, via the OMDb API.

IMDb publishes no public API. OMDb (omdbapi.com) serves IMDb's own data —
title, year, director, actors, IMDb ID and rating — through a free API key
(1,000 lookups/day, enough for a personal library).

Stdlib only (urllib). Network trouble never breaks a rename: any failure
just means the .nfo keeps its basic tags. Successful lookups are cached
locally so re-runs are free and instant.

API key resolution (first hit wins):
  1. --omdb-key on the command line
  2. OMDB_API_KEY environment variable
  3. a file containing just the key at:
       Windows: %APPDATA%\\mediatidy\\omdb.key
       other:   ~/.mediatidy/omdb.key
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

API_URL = "https://www.omdbapi.com/"
TIMEOUT = 12


def _config_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "mediatidy"
    return Path.home() / ".mediatidy"


def resolve_api_key(cli_key: str | None = None) -> str | None:
    if cli_key:
        return cli_key.strip()
    env_key = os.environ.get("OMDB_API_KEY", "").strip()
    if env_key:
        return env_key
    key_file = _config_dir() / "omdb.key"
    try:
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    return None


def _cache_file() -> Path:
    return _config_dir() / "omdb_cache.json"


def load_cache() -> dict:
    try:
        return json.loads(_cache_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_cache(cache: dict) -> None:
    try:
        d = _config_dir()
        d.mkdir(parents=True, exist_ok=True)
        _cache_file().write_text(json.dumps(cache, indent=1),
                                 encoding="utf-8")
    except OSError:
        pass  # caching is best-effort


def _clean(value: str | None) -> str | None:
    if not value or value.strip().upper() == "N/A":
        return None
    return value.strip()


def _parse_item(data: dict) -> dict | None:
    if data.get("Response") != "True":
        return None
    director = _clean(data.get("Director"))
    actors_raw = _clean(data.get("Actors"))
    genre_raw = _clean(data.get("Genre"))
    return {
        "title": _clean(data.get("Title")),
        "year": _clean(data.get("Year")),
        "director": None if not director or director == "N/A" else
                    director.split(",")[0].strip(),
        "actors": [a.strip() for a in actors_raw.split(",")] if actors_raw
                  else [],
        "genre": [g.strip() for g in genre_raw.split(",")] if genre_raw
                 else [],
        "imdb_id": _clean(data.get("imdbID")),
        "imdb_rating": _clean(data.get("imdbRating")),
    }


def _query(params: dict, api_key: str) -> dict | None:
    params = dict(params)
    params["apikey"] = api_key
    url = API_URL + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return _parse_item(data)


def enrich_movie(title: str, year: int, api_key: str,
                cache: dict | None = None) -> dict | None:
    """Look up a movie's director/actors/genre. Returns None on failure."""
    key = f"movie:{title.lower()}:{year}"
    cache = cache if cache is not None else load_cache()
    item = cache.get(key, "missing")
    # re-query entries cached before genre was collected
    if item == "missing" or (isinstance(item, dict) and "genre" not in item):
        item = _query({"t": title, "y": str(year), "type": "movie"}, api_key)
        cache[key] = item
        save_cache(cache)
    return item


def enrich_episode(show: str, season: int, episode: int, api_key: str,
                   cache: dict | None = None) -> dict | None:
    """Look up a TV episode's director/actors/genre. None on failure."""
    key = f"episode:{show.lower()}:{season}:{episode}"
    cache = cache if cache is not None else load_cache()
    item = cache.get(key, "missing")
    if item == "missing" or (isinstance(item, dict) and "genre" not in item):
        item = _query({"t": show, "Season": str(season),
                       "Episode": str(episode)}, api_key)
        cache[key] = item
        save_cache(cache)
    return item
