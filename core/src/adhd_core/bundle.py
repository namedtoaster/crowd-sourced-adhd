"""Reading a bundle off disk, and writing submission.json for one."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .result import canonical_json

MANIFEST = "submission.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_files(root: Path) -> tuple[list[str], list[str]]:
    """Every file under root except the manifest, as sorted posix paths.

    Returns (files, links). Symlinks are never followed: they are reported
    separately so the checks can reject them.
    """
    files: list[str] = []
    links: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            links.append(rel)
        elif path.is_file() and rel != MANIFEST:
            files.append(rel)
    return files, links


def safe_relpath(rel: str) -> bool:
    p = PurePosixPath(rel)
    return bool(rel) and not p.is_absolute() and ".." not in p.parts and "\\" not in rel


@dataclass
class Bundle:
    root: Path
    raw: bytes | None
    manifest: dict[str, Any] | None
    read_error: str | None

    @property
    def sha256(self) -> str:
        """Hash of the canonical manifest. It pins every file by hash."""
        if self.manifest is not None:
            return hashlib.sha256(canonical_json(self.manifest)).hexdigest()
        return hashlib.sha256(self.raw or b"").hexdigest()

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read_bytes(self, rel: str) -> bytes:
        return self.path(rel).read_bytes()

    def files_matching(self, pattern: str) -> list[str]:
        listed = [f["path"] for f in (self.manifest or {}).get("files", [])]
        return sorted(p for p in listed if PurePosixPath(p).match(pattern) and _same_depth(p, pattern))


def _same_depth(path: str, pattern: str) -> bool:
    # PurePosixPath.match anchors on the right, so "*.png" would match
    # "frames/a.png". Slot outputs mean the exact path, so require equal depth.
    return len(PurePosixPath(path).parts) == len(PurePosixPath(pattern).parts)


def load_bundle(root: Path) -> Bundle:
    root = Path(root)
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        return Bundle(root, None, None, f"There is no {MANIFEST} in {root}.")
    raw = manifest_path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return Bundle(root, raw, None, f"{MANIFEST} is not valid JSON: {exc}")
    if not isinstance(doc, dict):
        return Bundle(root, raw, None, f"{MANIFEST} must be a JSON object.")
    return Bundle(root, raw, doc, None)


def build_manifest(
    root: Path,
    slot: dict[str, Any],
    *,
    crew_no: int,
    name: str,
    signed_off_by: str,
    client: str,
    core: str,
    revision: int = 1,
    message: str | None = None,
    blender: str | None = None,
) -> dict[str, Any]:
    """Describes every file under root. Writing it is up to the caller."""
    files, _links = list_files(Path(root))
    doc: dict[str, Any] = {
        "schema": "adhd/submission@0",
        "slot": slot["id"],
        "film": slot["film"],
        "contributor": {"crew_no": crew_no, "name": name},
        "revision": revision,
        "files": [
            {"path": rel, "sha256": sha256_file(Path(root) / rel), "bytes": (Path(root) / rel).stat().st_size}
            for rel in files
        ],
        "tools": {"client": client, "core": core},
        "dco": {"version": "1.1", "signed_off_by": signed_off_by},
    }
    if message:
        doc["message"] = message
    if blender:
        doc["tools"]["blender"] = blender
    return doc
