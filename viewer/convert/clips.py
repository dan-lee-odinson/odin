"""The animation clips, made ready for VERDA's page.

Each clip of a run comes with a sync file beside it, a small JSON object:

    run_id              the run the clip shows
    timeline_sha256     the SHA-256 of the bytes of the timeline file it was rendered from
    first_frame_met_s   the MET its first frame shows
    met_step_s          the MET between one frame and the next
    fps                 its frames a second

so frame n shows MET first_frame_met_s + n * met_step_s, at n / fps seconds into the clip.

A page opened from disk can read neither a JSON file nor a file's bytes, so the
converter does both for it: it copies each clip and its sync file into the
output folder's clips/ folder, and writes each one's sync fields into index.js
beside each timeline file's SHA-256. The page plays a clip only when its sync
file's run_id and timeline_sha256 match the timeline on screen; that check is
the page's, so that a clip copied here from another rendering still shows why it
is not played.

A clip may also have a caption beside it, <stem>.caption.txt, the full caption
its renderer gives it. It is copied with the clip and its text listed with it in
index.js, for the page to show on request.

This module reads the clips folder it is given and writes only inside the
output folder's clips/ folder.
"""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

CLIPS = "clips"
CAPTION = ".caption.txt"
VIDEO_TYPES = (".mp4", ".webm", ".m4v", ".mov", ".ogv")
FIELDS = ("run_id", "timeline_sha256", "first_frame_met_s", "met_step_s", "fps")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_HEX = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")


class ClipError(Exception):
    pass


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def read_sync(path):
    """A sync file's fields, and what is wrong with it."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, ["%s cannot be read: %s" % (path.name, exc)]
    if not isinstance(data, dict):
        return {}, ["%s is not a JSON object" % path.name]
    problems = ["%s has no %s" % (path.name, key) for key in FIELDS if key not in data]
    sync = {key: data.get(key) for key in FIELDS}
    if not isinstance(sync["run_id"], str) or not sync["run_id"]:
        problems.append("%s: run_id is not a name" % path.name)
    m = _HEX.match(sync["timeline_sha256"] or "") if isinstance(sync["timeline_sha256"], str) else None
    if not m:
        problems.append("%s: timeline_sha256 is not a SHA-256" % path.name)
    else:
        sync["timeline_sha256"] = "sha256:" + m.group(1).lower()
    for key in ("first_frame_met_s", "met_step_s", "fps"):
        if not isinstance(sync[key], (int, float)) or isinstance(sync[key], bool):
            problems.append("%s: %s is not a number" % (path.name, key))
    for key in ("met_step_s", "fps"):
        if isinstance(sync[key], (int, float)) and not sync[key] > 0:
            problems.append("%s: %s is not above 0" % (path.name, key))
    return sync, problems


def clip_beside(sync_path):
    """The video file beside a sync file, named as it is: <stem>.sync.json or <stem>.json beside <stem>.<video>."""
    sync_path = Path(sync_path)
    name = sync_path.name
    stem = name[:-len(".sync.json")] if name.endswith(".sync.json") else name[:-len(".json")]
    found = [sync_path.with_name(stem + ext) for ext in VIDEO_TYPES if sync_path.with_name(stem + ext).is_file()]
    return found


def caption_beside(sync_path):
    """The clip's caption, <stem>.caption.txt beside its sync file, or None."""
    sync_path = Path(sync_path)
    name = sync_path.name
    stem = name[:-len(".sync.json")] if name.endswith(".sync.json") else name[:-len(".json")]
    caption = sync_path.with_name(stem + CAPTION)
    return caption if caption.is_file() else None


def sync_files(clips_dir):
    return sorted(p for p in Path(clips_dir).rglob("*.json") if p.is_file())


def place_clips(clips_dir, out_dir):
    """Copies each clip with a sound sync file, and that sync file, into <out_dir>/clips/.

    Yields (sync file, what was placed or None, problems)."""
    target = Path(out_dir) / CLIPS
    for sync_path in sync_files(clips_dir):
        sync, problems = read_sync(sync_path)
        found = clip_beside(sync_path)
        caption = caption_beside(sync_path)
        if len(found) != 1:
            problems.append("%s: %s" % (sync_path.name, "no clip beside it" if not found else
                                        "more than one clip beside it: %s" % ", ".join(p.name for p in found)))
        for p in [sync_path] + found + ([caption] if caption else []):
            if not _NAME.match(p.name):
                problems.append("%s cannot name a file in the output folder" % p.name)
        if problems:
            yield sync_path, None, problems
            continue
        target.mkdir(parents=True, exist_ok=True)
        for source in (found[0], sync_path):
            temporary = target / (source.name + ".tmp")
            shutil.copyfile(source, temporary)
            os.replace(temporary, target / source.name)
        placed = {"clip": found[0].name, "sync": sync_path.name}
        if caption:
            shutil.copyfile(caption, target / (caption.name + ".tmp"))
            os.replace(target / (caption.name + ".tmp"), target / caption.name)
            placed["caption"] = caption.name
        yield sync_path, placed, []


def index_entries(out_dir):
    """Every clip placed in <out_dir>/clips/, for index.js: its sync fields, its files and their hashes."""
    entries = []
    folder = Path(out_dir) / CLIPS
    if not folder.is_dir():
        return entries
    for sync_path in sorted(folder.glob("*.json")):
        sync, problems = read_sync(sync_path)
        found = clip_beside(sync_path)
        caption = caption_beside(sync_path)
        entry = dict(sync, sync_file="%s/%s" % (CLIPS, sync_path.name), sync_sha256=sha256_of(sync_path),
                     caption=caption.read_text(encoding="utf-8") if caption else None, problems=problems)
        if len(found) == 1:
            entry.update(file="%s/%s" % (CLIPS, found[0].name), clip_sha256=sha256_of(found[0]))
        else:
            entry.update(file=None, clip_sha256=None)
            entry["problems"] = problems + ["no single clip beside %s" % sync_path.name]
        entries.append(entry)
    return entries
