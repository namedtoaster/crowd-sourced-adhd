"""Checks a submission PR in CI.

Runs from the trusted checkout of main. The PR's checkout is read as data
and never executed, and its slot specs are ignored: the slot always comes
from main. That way a PR cannot loosen the rules it is judged by.

A submission PR may only add files inside one entry folder:

    films/<NN>/entries/<SLOT-ID>/<github id>/

Text files travel in the PR. Everything else is fetched from storage by
hash before checking, so binaries never enter Git.
"""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .bundle import load_bundle
from .result import Check, Result
from .runner import check_bundle
from .spec import SlotError, load_slot

ENTRY_PATH = re.compile(r"^films/(\d{2})/entries/([A-Z]+(?:-[A-Za-z0-9]+)+)/([1-9][0-9]*)/(.+)$")
TEXT_EXTENSIONS = {".md", ".json", ".usda"}
MAX_TEXT_BYTES = 256 * 1024
FETCH_TIMEOUT_S = 60
FORMAT_HINT = "films/NN/entries/SLOT-ID/GITHUB_ID/"


@dataclass(frozen=True)
class Entry:
    film: int
    film_dir: str
    slot_id: str
    contributor_id: int

    @property
    def path(self) -> str:
        return f"{self.film_dir}/entries/{self.slot_id}/{self.contributor_id}"


def resolve_entry(changed: list[str]) -> tuple[Entry | None, Check]:
    """Works out which entry a PR adds, or fails if it touches anything else."""
    changed = sorted({c.strip() for c in changed if c.strip()})
    if not changed:
        return None, Check("pr.scope", "fail", "The PR changes no files.",
                           fix="Submit through the Blender add-on, the web form or the desktop app.")
    outside = [c for c in changed if not ENTRY_PATH.match(c)]
    if outside:
        shown = ", ".join(outside[:10]) + (f" and {len(outside) - 10} more" if len(outside) > 10 else "")
        return None, Check("pr.scope", "fail",
                           f"A submission can only add files inside one entry folder, {FORMAT_HINT}. Outside it: {shown}.",
                           fix="Submit through the add-on, web form or app. Changes to tools, slots or CI go in their own PR for the owner to review.")
    entries = set()
    for c in changed:
        m = ENTRY_PATH.match(c)
        assert m
        entries.add((m.group(1), m.group(2), int(m.group(3))))
    if len(entries) > 1:
        listing = ", ".join(f"films/{f}/entries/{s}/{i}" for f, s, i in sorted(entries))
        return None, Check("pr.scope", "fail", f"The PR adds more than one entry: {listing}.",
                           fix="Send one entry per PR.")
    film_dir, slot_id, contributor_id = entries.pop()
    entry = Entry(int(film_dir), f"films/{film_dir}", slot_id, contributor_id)
    return entry, Check("pr.scope", "pass", f"The PR adds one entry, {entry.path}.", where=entry.path)


def check_repo_files(pr_root: Path, entry: Entry, changed: list[str]) -> Check:
    """Only small text files may be committed. Binaries belong in storage."""
    binaries, big = [], []
    for c in sorted(set(changed)):
        path = pr_root / c
        if not path.is_file():
            continue  # a deletion
        if PurePosixPath(c).suffix.lower() not in TEXT_EXTENSIONS:
            binaries.append(c)
        elif path.stat().st_size > MAX_TEXT_BYTES:
            big.append(c)
    if binaries:
        return Check("pr.binaries", "fail", "These files are committed to Git but must go to storage: " + ", ".join(binaries) + ".",
                     fix="Remove them from the PR. The client uploads them by hash; submission.json lists them.")
    if big:
        return Check("pr.binaries", "fail", f"These text files are over {MAX_TEXT_BYTES // 1024} KB: " + ", ".join(big) + ".",
                     fix="Large files go to storage, not Git.")
    return Check("pr.binaries", "pass", "Only small text files are committed.")


def fetch_missing(bundle_dir: Path, base_url: str | None) -> Check:
    """Downloads every listed file that is not in the PR, from base_url/<sha256>."""
    bundle = load_bundle(bundle_dir)
    if bundle.manifest is None or not isinstance(bundle.manifest.get("files"), list):
        return Check("pr.fetch", "skip", "No readable manifest, so nothing to fetch.")
    missing = [f for f in bundle.manifest["files"]
               if isinstance(f, dict) and isinstance(f.get("path"), str)
               and isinstance(f.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", f["sha256"])
               and not (bundle_dir / f["path"]).exists()]
    if not missing:
        return Check("pr.fetch", "pass", "Every file is in the PR. Nothing to fetch.")
    if not base_url:
        return Check("pr.fetch", "fail", f"{len(missing)} files are not in the PR and no storage is set up to fetch them from.",
                     fix="Set the ADHD_BLOB_BASE_URL repository variable, or commit the files if they are text.")
    problems: list[str] = []
    for f in missing:
        target = (bundle_dir / f["path"]).resolve()
        if bundle_dir.resolve() not in target.parents:
            problems.append(f"{f['path']} points outside the entry")
            continue
        url = f"{base_url.rstrip('/')}/{f['sha256']}"
        try:
            with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_S) as resp:
                data = resp.read(int(f.get("bytes", 0)) + 1)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            problems.append(f"{f['path']} could not be downloaded ({exc})")
            continue
        if hashlib.sha256(data).hexdigest() != f["sha256"]:
            problems.append(f"{f['path']} downloaded but its hash does not match")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if problems:
        return Check("pr.fetch", "fail", "Could not fetch every file: " + "; ".join(problems) + ".",
                     fix="Resubmit from your client so it uploads the files again.")
    return Check("pr.fetch", "pass", f"Fetched {len(missing)} files from storage by hash.")


def run_ci(trusted_root: Path, pr_root: Path, changed: list[str], blob_base_url: str | None = None) -> Result:
    """Every check for one submission PR. Raises SlotError only if main's slot spec is broken."""
    from . import __version__

    pre: list[Check] = []
    entry, scope = resolve_entry(changed)
    pre.append(scope)
    if entry is None:
        return Result(core=__version__, slot="unknown", bundle_sha256=hashlib.sha256(b"").hexdigest(), checks=pre)

    bundle_dir = pr_root / entry.path
    empty = Result(core=__version__, slot=entry.slot_id, bundle_sha256=load_bundle(bundle_dir).sha256)

    slot_path = trusted_root / entry.film_dir / "slots" / f"{entry.slot_id}.json"
    if not slot_path.is_file():
        pre.append(Check("pr.slot", "fail", f"There is no slot {entry.slot_id} in film {entry.film} on main.",
                         fix="Check the slot id. Only slots that exist on main take entries."))
        empty.checks = pre
        return empty
    slot = load_slot(slot_path)
    if slot["film"] != entry.film or slot["id"] != entry.slot_id:
        raise SlotError(f"{slot_path} says film {slot['film']}, slot {slot['id']}, which does not match its path.")
    pre.append(Check("pr.slot", "pass", f"Slot {entry.slot_id} exists on main.", where=str(slot_path.relative_to(trusted_root))))

    pre.append(check_repo_files(pr_root, entry, changed))

    manifest = load_bundle(bundle_dir).manifest
    contributor = (manifest or {}).get("contributor", {}) if isinstance(manifest, dict) else {}
    if isinstance(contributor, dict) and contributor.get("github_id") not in (None, entry.contributor_id):
        pre.append(Check("pr.contributor", "fail",
                         f"The entry folder is for GitHub id {entry.contributor_id} but submission.json says {contributor.get('github_id')}.",
                         fix="Resubmit from your client, which names the folder after your GitHub id."))

    if not any(c.status == "fail" for c in pre):
        pre.append(fetch_missing(bundle_dir, blob_base_url))

    if any(c.status == "fail" for c in pre):
        empty.checks = pre
        return empty

    result = check_bundle(bundle_dir, slot)
    result.checks = pre + result.checks
    return result


def summary_markdown(result: Result) -> str:
    """A short report for the GitHub job summary."""
    icon = {"pass": "ok", "fail": "**FAIL**", "skip": "skip"}
    lines = [f"### {result.slot}: {result.verdict.upper()}", "", "| | Check | Result |", "|---|---|---|"]
    for c in result.checks:
        text = c.message.replace("|", "\\|").replace("\n", " ")
        if c.fix:
            text += "<br>Fix: " + c.fix.replace("|", "\\|").replace("\n", "<br>")
        lines.append(f"| {icon[c.status]} | `{c.id}` | {text} |")
    return "\n".join(lines) + "\n"
