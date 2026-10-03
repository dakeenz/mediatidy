"""Read real technical metadata so filename claims can be verified.

Filenames lie: "1080p" in the name doesn't mean the file is 1080p.
When two versions of the same title exist, we probe the actual streams
with ffprobe (part of ffmpeg) instead of trusting the filename.
If ffprobe isn't installed, everything is reported unverified and the
planner says so — it never pretends.
"""
from __future__ import annotations

import json
import shutil
import subprocess


def probe_media(path: str) -> dict:
    """Return {verified, width, height, video_codec, audio_codec}.

    verified is False when ffprobe is missing or the probe fails.
    """
    result = {
        "verified": False,
        "width": None,
        "height": None,
        "video_codec": None,
        "audio_codec": None,
    }
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return result
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error",
             "-show_entries", "stream=index,codec_type,codec_name,width,height",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(proc.stdout or "{}")
    except Exception:
        return result
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and result["video_codec"] is None:
            result["video_codec"] = stream.get("codec_name")
            result["width"] = stream.get("width")
            result["height"] = stream.get("height")
        elif stream.get("codec_type") == "audio" and result["audio_codec"] is None:
            result["audio_codec"] = stream.get("codec_name")
    if result["width"] or result["video_codec"]:
        result["verified"] = True
    return result


def describe(info: dict) -> str:
    """One-line human summary, e.g. '1920x1080 h264 / aac'."""
    if not info.get("verified"):
        return "unverified (ffprobe not available)"
    v = info.get("video_codec") or "?"
    a = info.get("audio_codec") or "?"
    if info.get("width") and info.get("height"):
        return f"{info['width']}x{info['height']} {v} / {a}"
    return f"{v} / {a}"
