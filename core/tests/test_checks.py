from __future__ import annotations

import json
from pathlib import Path

import pytest

from adhd_core import check_bundle
from adhd_core.formats import count_words, read_png_header, split_front_matter
from adhd_core.spec import validate

from conftest import BOARDS_SLOT, GOOD_BEAT, LIGHT_SLOT, STORY_SLOT, boards_files, png_bytes

REPO = Path(__file__).resolve().parents[2]


def statuses(result) -> dict[str, str]:
    """Last status per check id, enough for these single file bundles."""
    return {c.id: c.status for c in result.checks}


def failed(result) -> list[str]:
    return [c.id for c in result.checks if c.status == "fail"]


# Formats

@pytest.mark.parametrize("text,n", [
    ("", 0),
    ("one two three", 3),
    ("Don't stop, half-lit SH-012!", 4),
    ("**Bold** _and_ `code`", 3),
    ("Steam — then nothing.", 3),
    ("café naïve", 2),
    ("- list\n- items", 2),
])
def test_word_count(text: str, n: int) -> None:
    assert count_words(text) == n


def test_front_matter() -> None:
    fm = split_front_matter(GOOD_BEAT)
    assert fm.present and fm.error is None
    assert fm.fields == {"location": "kitchen", "time_of_day": "late afternoon"}
    assert fm.body.startswith("The kettle")
    assert split_front_matter("---\nlocation: x\nno close").error
    assert split_front_matter("---\nNot a key line\n---\nbody").error
    assert not split_front_matter("Just a beat.").present


def test_png_header() -> None:
    assert read_png_header(png_bytes(1920, 1080)) is not None
    info = read_png_header(png_bytes(1920, 1080))
    assert (info.width, info.height) == (1920, 1080)
    assert read_png_header(b"GIF89a" + b"\x00" * 30) is None


# Bundle checks

def test_story_passes(make_bundle) -> None:
    result = check_bundle(make_bundle(STORY_SLOT, {"beat.md": GOOD_BEAT}), STORY_SLOT)
    assert result.verdict == "pass", result.to_dict()


def test_missing_manifest(make_bundle) -> None:
    result = check_bundle(make_bundle(STORY_SLOT, {"beat.md": GOOD_BEAT}, manifest=False), STORY_SLOT)
    assert failed(result) == ["bundle.manifest"]


def test_invalid_manifest(make_bundle) -> None:
    root = make_bundle(STORY_SLOT, {"beat.md": GOOD_BEAT})
    doc = json.loads((root / "submission.json").read_text())
    del doc["dco"]
    (root / "submission.json").write_text(json.dumps(doc))
    result = check_bundle(root, STORY_SLOT)
    assert failed(result) == ["bundle.manifest"]
    assert "dco" in result.checks[0].message


def test_wrong_slot(make_bundle) -> None:
    root = make_bundle(STORY_SLOT, {"beat.md": GOOD_BEAT})
    other = dict(STORY_SLOT, id="BEAT-05")
    assert failed(check_bundle(root, other)) == ["bundle.slot_match"]


def test_edited_after_bundling(make_bundle) -> None:
    root = make_bundle(STORY_SLOT, {"beat.md": GOOD_BEAT})
    (root / "beat.md").write_text(GOOD_BEAT + "One more line.")
    result = check_bundle(root, STORY_SLOT)
    assert failed(result) == ["bundle.files"]
    assert "changed after" in next(c for c in result.checks if c.id == "bundle.files").message
    # Hashes do not match, so the content checks must not run.
    assert "story.words" not in statuses(result)


def test_unlisted_and_out_of_scope(make_bundle) -> None:
    root = make_bundle(STORY_SLOT, {"beat.md": GOOD_BEAT, "notes.txt": "draft"})
    (root / "sneaky.md").write_text("later addition")
    result = check_bundle(root, STORY_SLOT)
    assert "bundle.unlisted" in failed(result)
    assert "bundle.scope" in failed(result)  # notes.txt is listed but not part of the slot


def test_path_escape_rejected(make_bundle) -> None:
    root = make_bundle(STORY_SLOT, {"beat.md": GOOD_BEAT})
    doc = json.loads((root / "submission.json").read_text())
    doc["files"].append({"path": "../outside.md", "sha256": "0" * 64, "bytes": 1})
    (root / "submission.json").write_text(json.dumps(doc))
    result = check_bundle(root, STORY_SLOT)
    # Either the schema pattern or the path check catches it; it never passes.
    assert result.verdict == "fail"


def test_missing_output(make_bundle) -> None:
    result = check_bundle(make_bundle(STORY_SLOT, {"story.md": GOOD_BEAT}), STORY_SLOT)
    assert "bundle.outputs" in failed(result)


# Story

def test_story_too_long(make_bundle) -> None:
    long_beat = GOOD_BEAT.split("---\n", 2)
    text = "---\n" + long_beat[1] + "---\n" + " ".join(["word"] * 81)
    result = check_bundle(make_bundle(STORY_SLOT, {"beat.md": text}), STORY_SLOT)
    assert failed(result) == ["story.words"]
    check = next(c for c in result.checks if c.id == "story.words")
    assert check.measured == 81 and check.limit == 80
    assert "Cut 1 word" in check.fix


def test_story_missing_fields(make_bundle) -> None:
    text = "---\nlocation: kitchen\n---\nThe kettle rattles."
    result = check_bundle(make_bundle(STORY_SLOT, {"beat.md": text}), STORY_SLOT)
    assert failed(result) == ["story.fields"]
    assert "time_of_day" in next(c for c in result.checks if c.id == "story.fields").message


def test_story_no_front_matter(make_bundle) -> None:
    result = check_bundle(make_bundle(STORY_SLOT, {"beat.md": "The kettle rattles."}), STORY_SLOT)
    assert failed(result) == ["story.fields"]


def test_story_not_utf8(make_bundle) -> None:
    result = check_bundle(make_bundle(STORY_SLOT, {"beat.md": b"\xff\xfe\x00bad"}), STORY_SLOT)
    assert failed(result) == ["story.format"]


# Storyboard

def test_boards_pass(make_bundle) -> None:
    result = check_bundle(make_bundle(BOARDS_SLOT, boards_files([(1920, 1080)] * 3)), BOARDS_SLOT)
    assert result.verdict == "pass", result.to_dict()


def test_boards_aspect_width_count(make_bundle) -> None:
    result = check_bundle(make_bundle(BOARDS_SLOT, boards_files([(1024, 768)])), BOARDS_SLOT)
    assert set(failed(result)) == {"boards.count", "boards.aspect", "boards.width"}


def test_boards_inconsistent_sizes(make_bundle) -> None:
    result = check_bundle(make_bundle(BOARDS_SLOT, boards_files([(1920, 1080), (1280, 720)])), BOARDS_SLOT)
    assert failed(result) == ["boards.consistent"]


def test_boards_unlisted_frame(make_bundle) -> None:
    files = boards_files([(1920, 1080)] * 2)
    files["frames/03.png"] = png_bytes(1920, 1080)
    result = check_bundle(make_bundle(BOARDS_SLOT, files), BOARDS_SLOT)
    assert failed(result) == ["boards.index"]
    assert "frames/03.png" in next(c for c in result.checks if c.id == "boards.index").message


def test_boards_not_png_and_too_big(make_bundle) -> None:
    files = boards_files([(1920, 1080)] * 2)
    files["frames/01.png"] = b"GIF89a" + b"\x00" * 64
    files["frames/02.png"] = png_bytes(1920, 1080, pad=2 * 1024 * 1024)
    result = check_bundle(make_bundle(BOARDS_SLOT, files), BOARDS_SLOT)
    assert set(failed(result)) == {"boards.image", "boards.size"}


def test_boards_no_index(make_bundle) -> None:
    files = boards_files([(1920, 1080)] * 2)
    del files["boards.json"]
    result = check_bundle(make_bundle(BOARDS_SLOT, files), BOARDS_SLOT)
    assert "boards.index" in failed(result)


# Results

def test_unbuilt_role_is_incomplete(make_bundle) -> None:
    result = check_bundle(make_bundle(LIGHT_SLOT, {"lights.usda": "#usda 1.0\n"}), LIGHT_SLOT)
    assert result.verdict == "incomplete"
    assert statuses(result)["role.checks"] == "skip"


def test_results_are_deterministic_and_valid(make_bundle) -> None:
    root = make_bundle(BOARDS_SLOT, boards_files([(1024, 768)]))
    a, b = check_bundle(root, BOARDS_SLOT), check_bundle(root, BOARDS_SLOT)
    assert a.to_json() == b.to_json()
    assert validate("check-result", a.to_dict()) is None
    assert all(c.fix for c in a.checks if c.status == "fail")


def test_spec_examples_validate() -> None:
    examples = REPO / "spec" / "examples"
    pairs = {"slot-beat": "slot", "slot-light": "slot", "submission": "submission", "check-result": "check-result"}
    for name, schema in pairs.items():
        assert validate(schema, json.loads((examples / f"{name}.json").read_text())) is None, name


def test_slot_schema_rejects_wrong_limits() -> None:
    bad = dict(LIGHT_SLOT, limits={"max_words": 80})
    assert validate("slot", bad) is not None
    for slot in (STORY_SLOT, BOARDS_SLOT, LIGHT_SLOT):
        assert validate("slot", slot) is None
