"""Kodi-compatible .nfo sidecar files.

What is an .nfo sidecar? A tiny XML file that sits next to a video, e.g.
    UHF (1989).mp4  ->  UHF (1989).nfo
Media managers (Kodi, Jellyfin, Emby) read these for title, year and tags.
It's an open, plain-text standard — nothing is locked in, and any player
or script can read them. The Auto Playlist Builder VLC extension already
reads <genre> tags from .nfo files, so tags written here flow straight
into themed playlists later.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path


def build_movie_nfo(title: str, year: int, tags: list[str],
                    director: str | None = None,
                    actors: list[str] | None = None,
                    genres: list[str] | None = None,
                    imdb_id: str | None = None,
                    imdb_rating: str | None = None) -> str:
    movie = ET.Element("movie")
    ET.SubElement(movie, "title").text = title
    ET.SubElement(movie, "year").text = str(year)
    if director:
        ET.SubElement(movie, "director").text = director
    for name in actors or []:
        actor = ET.SubElement(movie, "actor")
        ET.SubElement(actor, "name").text = name
    for genre in genres or []:
        ET.SubElement(movie, "genre").text = genre
    if imdb_id:
        ET.SubElement(movie, "imdbid").text = imdb_id
    if imdb_rating:
        ET.SubElement(movie, "rating").text = imdb_rating
    for tag in tags:
        ET.SubElement(movie, "genre").text = tag
    rough = ET.tostring(movie, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(
        indent="  ", encoding="UTF-8").decode("utf-8")


def build_episode_nfo(title: str, season: int, episode: int, year: int,
                      tags: list[str],
                      director: str | None = None,
                      actors: list[str] | None = None,
                      genres: list[str] | None = None,
                      imdb_id: str | None = None,
                      imdb_rating: str | None = None) -> str:
    ep = ET.Element("episodedetails")
    ET.SubElement(ep, "title").text = title
    ET.SubElement(ep, "season").text = str(season)
    ET.SubElement(ep, "episode").text = str(episode)
    if year:
        ET.SubElement(ep, "year").text = str(year)
    if director:
        ET.SubElement(ep, "director").text = director
    for name in actors or []:
        actor = ET.SubElement(ep, "actor")
        ET.SubElement(actor, "name").text = name
    for genre in genres or []:
        ET.SubElement(ep, "genre").text = genre
    if imdb_id:
        ET.SubElement(ep, "imdbid").text = imdb_id
    if imdb_rating:
        ET.SubElement(ep, "rating").text = imdb_rating
    for tag in tags:
        ET.SubElement(ep, "genre").text = tag
    rough = ET.tostring(ep, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(
        indent="  ", encoding="UTF-8").decode("utf-8")


def write_nfo(video_path: Path, title: str, year: int,
              tags: list[str], season: int | None = None,
              episode: int | None = None,
              director: str | None = None,
              actors: list[str] | None = None,
              genres: list[str] | None = None,
              imdb_id: str | None = None,
              imdb_rating: str | None = None) -> Path:
    nfo_path = video_path.with_suffix(".nfo")
    if season is not None and episode is not None:
        text = build_episode_nfo(title, season, episode, year, tags,
                                 director=director, actors=actors,
                                 genres=genres, imdb_id=imdb_id,
                                 imdb_rating=imdb_rating)
    else:
        text = build_movie_nfo(title, year, tags, director=director,
                               actors=actors, genres=genres, imdb_id=imdb_id,
                               imdb_rating=imdb_rating)
    nfo_path.write_text(text, encoding="utf-8")
    return nfo_path
