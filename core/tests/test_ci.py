from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from adhd_core.bundle import MANIFEST, build_manifest
from adhd_core.ci import resolve_entry, run_ci
from adhd_core.cli import main

from conftest import BOARDS_SLOT, GOOD_BEAT, STORY_SLOT, boards_files, png_bytes

STORY = dict(STORY_SLOT, film=0, id="BEAT-01")
BOARDS = dict(BOARDS_SLOT, film=0, id="SH-001-boards")
ENTRY = "films/00/entries/BEAT-01/1000001"
BOARDS_ENTRY = "films/00/entries/SH-001-boards/1000001"


@pytest.fixture
def repos(tmp_path: Path):
    trusted, pr = tmp_path / "trusted", tmp_path / "pr"
    for slot in (STORY, BOARDS):
        path = trusted / "films/00/slots" / f"{slot['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(slot))
    pr.mkdir()
    return trusted, pr


def add_entry(pr: Path, entry: str, slot: dict, files: dict, crew_no: int = 1000001) -> list[str]:
    """Writes files into the PR checkout, bundles them, returns the changed paths."""
    root = pr / entry
    root.mkdir(parents=True)
    for rel, content in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(content.encode() if isinstance(content, str) else content)
    doc = build_manifest(root, slot, crew_no=crew_no, display_name="example_writer",
                         signed_off_by="example_writer", client="tests", core="0.1.0")
    (root / MANIFEST).write_text(json.dumps(doc))
    return sorted(f"{entry}/{p.relative_to(root).as_posix()}" for p in root.rglob("*") if p.is_file())


def by_id(result) -> dict[str, str]:
    return {c.id: c.status for c in result.checks}


def test_good_entry_passes(repos) -> None:
    trusted, pr = repos
    changed = add_entry(pr, ENTRY, STORY, {"beat.md": GOOD_BEAT})
    result = run_ci(trusted, pr, changed)
    assert result.verdict == "pass", result.to_dict()
    assert by_id(result)["pr.scope"] == "pass"


@pytest.mark.parametrize("extra", [
    "core/src/adhd_core/checks/story.py",       # loosen the checker
    "films/00/slots/BEAT-01.json",              # loosen the slot
    ".github/workflows/check-submission.yml",   # skip the check
    "films/00/entries/BEAT-01/beat.md",         # no contributor folder
])
def test_touching_anything_else_fails(repos, extra: str) -> None:
    trusted, pr = repos
    changed = add_entry(pr, ENTRY, STORY, {"beat.md": GOOD_BEAT}) + [extra]
    result = run_ci(trusted, pr, changed)
    assert result.verdict == "fail"
    assert [c.id for c in result.checks] == ["pr.scope"]
    assert extra in result.checks[0].message


def test_slot_comes_from_main_not_the_pr(repos) -> None:
    trusted, pr = repos
    changed = add_entry(pr, ENTRY, STORY, {"beat.md": GOOD_BEAT + " word" * 100})
    # A loosened copy of the slot in the PR checkout is ignored.
    loose = pr / "films/00/slots/BEAT-01.json"
    loose.parent.mkdir(parents=True)
    loose.write_text(json.dumps(dict(STORY, limits={"max_words": 9999})))
    assert run_ci(trusted, pr, changed).verdict == "fail"


def test_two_entries_fail(repos) -> None:
    trusted, pr = repos
    changed = add_entry(pr, ENTRY, STORY, {"beat.md": GOOD_BEAT})
    changed += add_entry(pr, "films/00/entries/BEAT-01/1000002", STORY, {"beat.md": GOOD_BEAT}, crew_no=1000002)
    result = run_ci(trusted, pr, changed)
    assert "more than one entry" in result.checks[0].message


def test_unknown_slot(repos) -> None:
    trusted, pr = repos
    changed = add_entry(pr, "films/00/entries/BEAT-99/1000001", dict(STORY, id="BEAT-99"), {"beat.md": GOOD_BEAT})
    result = run_ci(trusted, pr, changed)
    assert by_id(result)["pr.slot"] == "fail"


def test_folder_must_match_contributor(repos) -> None:
    trusted, pr = repos
    changed = add_entry(pr, "films/00/entries/BEAT-01/1000002", STORY, {"beat.md": GOOD_BEAT}, crew_no=1000001)
    assert by_id(run_ci(trusted, pr, changed))["pr.contributor"] == "fail"


def test_binary_in_git_fails(repos) -> None:
    trusted, pr = repos
    changed = add_entry(pr, BOARDS_ENTRY, BOARDS, boards_files([(1920, 1080)] * 2))
    result = run_ci(trusted, pr, changed)
    assert by_id(result)["pr.binaries"] == "fail"


def test_binaries_fetched_from_storage(repos, tmp_path: Path) -> None:
    trusted, pr = repos
    changed = add_entry(pr, BOARDS_ENTRY, BOARDS, boards_files([(1920, 1080)] * 2))
    # Move the PNGs into a fake storage bucket named by hash, as the client would.
    store = tmp_path / "store"
    store.mkdir()
    for rel in [c for c in changed if c.endswith(".png")]:
        data = (pr / rel).read_bytes()
        (store / hashlib.sha256(data).hexdigest()).write_bytes(data)
        (pr / rel).unlink()
    changed = [c for c in changed if not c.endswith(".png")]

    no_store = run_ci(trusted, pr, changed)
    assert by_id(no_store)["pr.fetch"] == "fail"

    result = run_ci(trusted, pr, changed, store.as_uri())
    assert result.verdict == "pass", result.to_dict()
    assert by_id(result)["pr.fetch"] == "pass"


def test_tampered_blob_rejected(repos, tmp_path: Path) -> None:
    trusted, pr = repos
    changed = add_entry(pr, BOARDS_ENTRY, BOARDS, boards_files([(1920, 1080)] * 2))
    store = tmp_path / "store"
    store.mkdir()
    for rel in [c for c in changed if c.endswith(".png")]:
        data = (pr / rel).read_bytes()
        (store / hashlib.sha256(data).hexdigest()).write_bytes(png_bytes(640, 480))  # wrong bytes
        (pr / rel).unlink()
    changed = [c for c in changed if not c.endswith(".png")]
    result = run_ci(trusted, pr, changed, store.as_uri())
    assert by_id(result)["pr.fetch"] == "fail"
    assert "hash does not match" in next(c for c in result.checks if c.id == "pr.fetch").message


def test_resolve_entry_rejects_empty() -> None:
    entry, check = resolve_entry([])
    assert entry is None and check.status == "fail"


def test_cli_ci(repos, tmp_path: Path, capsys) -> None:
    trusted, pr = repos
    changed = add_entry(pr, ENTRY, STORY, {"beat.md": GOOD_BEAT})
    changed_file = tmp_path / "changed.txt"
    changed_file.write_text("\n".join(changed))
    summary = tmp_path / "summary.md"
    out = tmp_path / "result.json"
    code = main(["ci", "--trusted", str(trusted), "--pr", str(pr), "--changed", str(changed_file),
                 "--json-out", str(out), "--summary", str(summary)])
    assert code == 0
    assert json.loads(out.read_text())["verdict"] == "pass"
    assert "BEAT-01: PASS" in summary.read_text()


def test_real_sandbox_entry_passes() -> None:
    """The example entry committed in films/00 must always pass against main's slots."""
    repo = Path(__file__).resolve().parents[2]
    entry = repo / ENTRY
    if not entry.exists():
        pytest.skip("no sandbox entry in this checkout")
    changed = [f"{ENTRY}/{p.relative_to(entry).as_posix()}" for p in entry.rglob("*") if p.is_file()]
    assert run_ci(repo, repo, changed).verdict == "pass"
