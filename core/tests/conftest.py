from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any, Callable

import pytest

from adhd_core.bundle import MANIFEST, build_manifest
from adhd_core.result import canonical_json
import json


def png_bytes(width: int, height: int, pad: int = 0) -> bytes:
    """A minimal PNG: signature, IHDR, IEND. Enough for header checks."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    extra = chunk(b"tEXt", b"pad\x00" + b"x" * pad) if pad else b""
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + extra + chunk(b"IEND", b"")


STORY_SLOT: dict[str, Any] = {
    "schema": "adhd/slot@0", "id": "BEAT-04", "film": 1, "phase": "story", "role": "story",
    "mode": "open-call", "title": "Beat 4", "brief": "The kettle boils over.",
    "outputs": [{"path": "beat.md", "kind": "markdown"}],
    "limits": {"max_words": 80, "required_fields": ["location", "time_of_day"]},
}

BOARDS_SLOT: dict[str, Any] = {
    "schema": "adhd/slot@0", "id": "SH-012-boards", "film": 1, "phase": "story", "role": "storyboard",
    "mode": "open-call", "title": "Boards, SH-012", "brief": "Boards for the kettle shot.", "shot": "SH-012",
    "outputs": [{"path": "boards.json", "kind": "json"}, {"path": "frames/*.png", "kind": "png"}],
    "limits": {"frames": {"min": 2, "max": 6}, "aspect": "16:9", "min_width_px": 1280, "max_file_mb": 1},
}

LIGHT_SLOT: dict[str, Any] = {
    "schema": "adhd/slot@0", "id": "SH-012-light", "film": 1, "phase": "assets-look", "role": "lighting",
    "mode": "claim", "title": "Lighting, SH-012", "brief": "Late afternoon.", "shot": "SH-012",
    "outputs": [{"path": "lights.usda", "kind": "usd-layer"}],
    "limits": {"max_lights": 6, "max_shadow_lights": 2},
}

GOOD_BEAT = """---
location: kitchen
time_of_day: late afternoon
---
The kettle starts to rattle. Steam fogs the window. Nobody moves to turn it off.
"""


@pytest.fixture
def make_bundle(tmp_path: Path) -> Callable[..., Path]:
    """Writes files into a fresh folder and bundles them for the slot."""
    counter = {"n": 0}

    def _make(slot: dict[str, Any], files: dict[str, bytes | str], *, manifest: bool = True) -> Path:
        counter["n"] += 1
        root = tmp_path / f"bundle{counter['n']}"
        root.mkdir()
        for rel, content in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        if manifest:
            doc = build_manifest(root, slot, crew_no=1000001, name="Example Writer",
                                 signed_off_by="Example Writer",
                                 client="tests", core="0.1.0")
            (root / MANIFEST).write_text(json.dumps(doc), encoding="utf-8")
        return root

    return _make


def boards_files(sizes: list[tuple[int, int]], **over: Any) -> dict[str, bytes | str]:
    files: dict[str, bytes | str] = {}
    frames = []
    for n, (w, h) in enumerate(sizes, start=1):
        rel = f"frames/{n:02d}.png"
        files[rel] = png_bytes(w, h)
        frames.append({"file": rel, "hold_frames": 24})
    files["boards.json"] = json.dumps({"frames": frames})
    files.update(over)
    return files


__all__ = ["png_bytes", "canonical_json", "STORY_SLOT", "BOARDS_SLOT", "LIGHT_SLOT", "GOOD_BEAT", "boards_files"]
