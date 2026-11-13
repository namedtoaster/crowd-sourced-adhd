"""Checks every bundle goes through, whatever the role."""

from __future__ import annotations

from typing import Any

from ..bundle import Bundle, list_files, safe_relpath, sha256_file
from ..result import Check
from ..spec import validate

EXTENSIONS = {
    "markdown": (".md",),
    "json": (".json",),
    "png": (".png",),
    "usd-layer": (".usda",),
    "usd-asset": (".usd", ".usda", ".usdc", ".usdz"),
    "gltf": (".gltf", ".glb"),
    "material-recipe": (".json",),
    "wav": (".wav",),
}


def check_manifest(bundle: Bundle, slot: dict[str, Any]) -> list[Check]:
    """Manifest readable, valid and for this slot. If not, nothing else can run."""
    if bundle.manifest is None:
        return [Check("bundle.manifest", "fail", bundle.read_error or "submission.json could not be read.",
                      fix="Rebuild the bundle with your client, or run adhd bundle on the folder.")]
    problem = validate("submission", bundle.manifest)
    if problem:
        return [Check("bundle.manifest", "fail", f"submission.json is not valid: {problem}.",
                      fix="Rebuild the bundle with your client, or run adhd bundle on the folder.")]
    out = [Check("bundle.manifest", "pass", "submission.json is valid.")]
    m = bundle.manifest
    if m["slot"] != slot["id"] or m["film"] != slot["film"]:
        out.append(Check("bundle.slot_match", "fail",
                         f"This bundle is for {m['slot']} in film {m['film']}, but it was checked against {slot['id']} in film {slot['film']}.",
                         fix="Check it against the slot it was made for, or rebuild it for this slot."))
    else:
        out.append(Check("bundle.slot_match", "pass", f"Bundle is for {slot['id']}."))
    return out


def check_files(bundle: Bundle) -> list[Check]:
    """Listed files exist with the right hash and size, and nothing else is in the folder."""
    assert bundle.manifest is not None
    listed = bundle.manifest["files"]
    on_disk, links = list_files(bundle.root)
    out: list[Check] = []

    bad_paths = sorted(f["path"] for f in listed if not safe_relpath(f["path"]))
    dupes = sorted({f["path"] for f in listed if [g["path"] for g in listed].count(f["path"]) > 1})
    if bad_paths or dupes:
        bad = ", ".join(bad_paths + dupes)
        return [Check("bundle.files", "fail", f"These file paths are not allowed or are listed twice: {bad}.",
                      fix="Paths must be relative, inside the bundle, and listed once. Rebuild the bundle.")]

    problems: list[str] = []
    for f in listed:
        path = bundle.path(f["path"])
        if f["path"] in links:
            problems.append(f"{f['path']} is a link")
        elif not path.is_file():
            problems.append(f"{f['path']} is missing")
        elif path.stat().st_size != f["bytes"] or sha256_file(path) != f["sha256"]:
            problems.append(f"{f['path']} changed after the bundle was made")
    if problems:
        out.append(Check("bundle.files", "fail", "Files do not match submission.json: " + "; ".join(problems) + ".",
                         fix="Rebuild the bundle after your last edit, so the manifest matches the files."))
    else:
        out.append(Check("bundle.files", "pass", f"All {len(listed)} listed files match their hashes."))

    listed_paths = {f["path"] for f in listed}
    extra = sorted((set(on_disk) | set(links)) - listed_paths)
    if extra:
        out.append(Check("bundle.unlisted", "fail", "Files in the folder that submission.json does not list: " + ", ".join(extra) + ".",
                         fix="Remove them, or rebuild the bundle so they are listed."))
    else:
        out.append(Check("bundle.unlisted", "pass", "No unlisted files."))
    return out


def check_outputs(bundle: Bundle, slot: dict[str, Any]) -> list[Check]:
    """Every output the slot asks for is present, of the right type, and nothing outside the slot."""
    assert bundle.manifest is not None
    listed = sorted(f["path"] for f in bundle.manifest["files"])
    out: list[Check] = []
    missing: list[str] = []
    wrong_type: list[str] = []
    claimed: set[str] = set()
    for output in slot["outputs"]:
        matches = bundle.files_matching(output["path"])
        if not matches:
            missing.append(output["path"])
        for rel in matches:
            claimed.add(rel)
            if not rel.lower().endswith(EXTENSIONS[output["kind"]]):
                wrong_type.append(f"{rel} (expected {output['kind']})")
    if missing:
        out.append(Check("bundle.outputs", "fail", "The slot needs these and the bundle does not have them: " + ", ".join(missing) + ".",
                         fix="Add the missing files with exactly these names."))
    elif wrong_type:
        out.append(Check("bundle.outputs", "fail", "Wrong file type: " + ", ".join(wrong_type) + ".",
                         fix="Export in the format the slot asks for."))
    else:
        out.append(Check("bundle.outputs", "pass", "Every file the slot asks for is there."))
    stray = [p for p in listed if p not in claimed]
    if stray:
        out.append(Check("bundle.scope", "fail", "These files are not part of this slot: " + ", ".join(stray) + ".",
                         fix="Remove them. A slot only takes the files listed in its spec."))
    else:
        out.append(Check("bundle.scope", "pass", "Nothing outside the slot."))
    return out
