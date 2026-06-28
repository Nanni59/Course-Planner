#!/usr/bin/env python3
"""
update_manifest.py  —  Course Planner video gallery helper

Run this AFTER you drop a new .mp4 into the ./videos/ folder (e.g. one rendered by
tools/manim_video_tool.ipynb). It scans ./videos/ for .mp4 files and rewrites
./videos/manifest.json so the site's Video Library can list them.

What it does:
  - Keeps the title / subject / date you already set for existing videos
    (so re-running it never clobbers your edits).
  - Adds any new .mp4 it finds, guessing a title from the filename, leaving the
    subject blank for you to fill in, and dating it from the file's timestamp.
  - Drops entries whose .mp4 has been deleted.
  - Sorts newest-first and prints exactly what changed.

Usage:
    python update_manifest.py

Then commit BOTH the new .mp4 and the updated videos/manifest.json.

No dependencies beyond the Python standard library.
"""

import json
import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VIDEOS_DIR = ROOT / "videos"
MANIFEST = VIDEOS_DIR / "manifest.json"


def pretty_title(filename: str) -> str:
    """Turn 'dot-product_intro.mp4' into 'Dot Product Intro'."""
    stem = Path(filename).stem
    words = stem.replace("-", " ").replace("_", " ").split()
    return " ".join(w[:1].upper() + w[1:] for w in words) if words else stem


def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            data = json.loads(MANIFEST.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("videos"), list):
                return data
            print("! manifest.json was malformed — starting a fresh one.")
        except json.JSONDecodeError as e:
            print(f"! manifest.json could not be parsed ({e}) — starting a fresh one.")
    return {"videos": []}


def main() -> int:
    if not VIDEOS_DIR.exists():
        print(f"! No videos/ folder found at {VIDEOS_DIR}. Create it and add .mp4 files first.")
        return 1

    manifest = load_manifest()
    existing = {v.get("file"): v for v in manifest.get("videos", []) if isinstance(v, dict) and v.get("file")}

    mp4_files = sorted(p.name for p in VIDEOS_DIR.glob("*.mp4"))
    found = set(mp4_files)

    added, removed, kept = [], [], []
    new_videos = []

    for name in mp4_files:
        if name in existing:
            new_videos.append(existing[name])
            kept.append(name)
        else:
            mtime = (VIDEOS_DIR / name).stat().st_mtime
            new_videos.append({
                "title": pretty_title(name),
                "file": name,
                "subject": "",
                "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
            })
            added.append(name)

    for name in existing:
        if name not in found:
            removed.append(name)

    # Newest first (by date string, then title). Undated entries sort last.
    new_videos.sort(key=lambda v: (v.get("date") or "0000-00-00", v.get("title", "")), reverse=True)
    manifest["videos"] = new_videos

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Scanned {VIDEOS_DIR}")
    print(f"  {len(found)} .mp4 file(s) present, {len(new_videos)} entr(y/ies) in manifest.")
    if added:
        print("  + added:   " + ", ".join(added))
        print("    (set a 'subject' for these in videos/manifest.json if you want)")
    if removed:
        print("  - removed: " + ", ".join(removed) + "  (file no longer present)")
    if kept and not added and not removed:
        print("  no changes — manifest already up to date.")
    print(f"\nWrote {MANIFEST.relative_to(ROOT)}")
    print("Next: commit the new .mp4(s) and videos/manifest.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
