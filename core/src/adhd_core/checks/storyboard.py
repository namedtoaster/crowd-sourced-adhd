"""Storyboards: boards.json giving the frame order, plus one PNG per frame.

boards.json looks like:

    {"frames": [{"file": "frames/01.png", "hold_frames": 24, "note": "Kettle, wide"}, ...]}
"""

from __future__ import annotations

import json
from typing import Any

from ..bundle import Bundle
from ..formats import read_png_header
from ..result import Check

INDEX = "boards.json"
ASPECT_TOLERANCE = 0.01  # 1 percent, so 1920x1080 and 1918x1080 both pass 16:9


def _read_index(bundle: Bundle) -> tuple[list[dict[str, Any]] | None, str | None]:
    try:
        doc = json.loads(bundle.read_bytes(INDEX).decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, f"{INDEX} could not be read: {exc}."
    frames = doc.get("frames") if isinstance(doc, dict) else None
    if not isinstance(frames, list) or not frames:
        return None, f'{INDEX} needs a "frames" list with at least one frame.'
    for n, frame in enumerate(frames, start=1):
        if not isinstance(frame, dict) or not isinstance(frame.get("file"), str):
            return None, f'Frame {n} in {INDEX} needs a "file".'
        hold = frame.get("hold_frames")
        if hold is not None and (not isinstance(hold, int) or isinstance(hold, bool) or hold < 1):
            return None, f'Frame {n} in {INDEX}: "hold_frames" must be a whole number of 1 or more.'
    return frames, None


def check_storyboard(bundle: Bundle, slot: dict[str, Any]) -> list[Check]:
    limits = slot["limits"]
    assert bundle.manifest is not None
    listed = {f["path"] for f in bundle.manifest["files"]}
    if INDEX not in listed:
        return [Check("boards.index", "fail", f"There is no {INDEX}.",
                      fix=f'Add {INDEX} listing the frames in order: {{"frames": [{{"file": "frames/01.png"}}]}}.')]
    frames, error = _read_index(bundle)
    if error or frames is None:
        return [Check("boards.index", "fail", error or f"{INDEX} is empty.", where=INDEX,
                      fix=f'Fix {INDEX}: {{"frames": [{{"file": "frames/01.png", "hold_frames": 24}}]}}.')]

    out: list[Check] = []
    files = [f["file"] for f in frames]
    pngs = sorted(p for p in listed if p.lower().endswith(".png"))
    missing = [f for f in files if f not in listed]
    unused = [p for p in pngs if p not in files]
    repeated = sorted({f for f in files if files.count(f) > 1})
    if missing or unused or repeated:
        parts = []
        if missing:
            parts.append("listed but not in the bundle: " + ", ".join(missing))
        if unused:
            parts.append("in the bundle but not listed: " + ", ".join(unused))
        if repeated:
            parts.append("listed more than once: " + ", ".join(repeated))
        detail = "; ".join(parts)
        out.append(Check("boards.index", "fail", f"{INDEX} and the images disagree. {detail[0].upper()}{detail[1:]}.",
                         where=INDEX, fix=f"Make {INDEX} list every frame image exactly once, in order."))
    else:
        out.append(Check("boards.index", "pass", f"{INDEX} lists all {len(files)} frames.", where=INDEX))

    lo, hi = limits["frames"].get("min", 1), limits["frames"].get("max")
    count = len(files)
    if count < lo or (hi is not None and count > hi):
        span = f"{lo} to {hi}" if hi is not None else f"at least {lo}"
        out.append(Check("boards.count", "fail", f"{count} frames. The shot list calls for {span}.",
                         measured=count, limit=limits["frames"],
                         fix="Add or merge frames to match the shot list."))
    else:
        out.append(Check("boards.count", "pass", f"{count} frames.", measured=count, limit=limits["frames"]))

    aw, ah = (int(x) for x in limits["aspect"].split(":"))
    target = aw / ah
    min_w = limits["min_width_px"]
    max_bytes = int(limits["max_file_mb"] * 1024 * 1024) if "max_file_mb" in limits else None
    sizes: dict[str, tuple[int, int]] = {}
    for rel in sorted(set(files) & listed):
        data = bundle.read_bytes(rel)
        info = read_png_header(data)
        if info is None:
            out.append(Check("boards.image", "fail", f"{rel} is not a PNG.", where=rel,
                             fix="Export the frame as PNG."))
            continue
        sizes[rel] = (info.width, info.height)
        if abs(info.width / info.height - target) / target > ASPECT_TOLERANCE:
            out.append(Check("boards.aspect", "fail", f"{rel} is {info.width}x{info.height}, which is not {limits['aspect']}.",
                             measured=f"{info.width}x{info.height}", limit=limits["aspect"], where=rel,
                             fix=f"Crop or resize the canvas to {limits['aspect']}, for example {min_w}x{round(min_w * ah / aw)}."))
        if info.width < min_w:
            out.append(Check("boards.width", "fail", f"{rel} is {info.width} px wide. The slot needs at least {min_w}.",
                             measured=info.width, limit=min_w, where=rel,
                             fix=f"Export at {min_w} px wide or more."))
        if max_bytes is not None and len(data) > max_bytes:
            mb = len(data) / (1024 * 1024)
            out.append(Check("boards.size", "fail", f"{rel} is {mb:.1f} MB. The slot allows {limits['max_file_mb']} MB.",
                             measured=round(mb, 1), limit=limits["max_file_mb"], where=rel,
                             fix="Export with more compression or fewer colours."))

    if sizes and not any(c.id in ("boards.image", "boards.aspect", "boards.width", "boards.size") for c in out):
        out.append(Check("boards.image", "pass", f"Every frame is a {limits['aspect']} PNG at least {min_w} px wide."))
    if len(set(sizes.values())) > 1:
        listing = ", ".join(f"{rel} {w}x{h}" for rel, (w, h) in sorted(sizes.items()))
        out.append(Check("boards.consistent", "fail", f"Frames are not all the same size: {listing}.",
                         fix="Export every frame from the same canvas size."))
    return out
