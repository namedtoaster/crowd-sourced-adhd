from __future__ import annotations

import json
from pathlib import Path

from adhd_core.cli import main

from conftest import GOOD_BEAT, STORY_SLOT


def test_bundle_then_check(tmp_path: Path, capsys) -> None:
    slot_path = tmp_path / "BEAT-04.json"
    slot_path.write_text(json.dumps(STORY_SLOT))
    work = tmp_path / "work"
    work.mkdir()
    (work / "beat.md").write_text(GOOD_BEAT)

    assert main(["bundle", str(work), "--slot", str(slot_path), "--crew-no", "1000001",
                 "--display-name", "example_writer"]) == 0
    assert (work / "submission.json").is_file()

    assert main(["check", str(work), "--slot", str(slot_path)]) == 0
    assert "BEAT-04  PASS" in capsys.readouterr().out

    (work / "beat.md").write_text(GOOD_BEAT + " extra")
    assert main(["check", str(work), "--slot", str(slot_path), "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "fail"


def test_broken_slot_is_usage_error(tmp_path: Path, capsys) -> None:
    slot_path = tmp_path / "bad.json"
    slot_path.write_text(json.dumps({"schema": "adhd/slot@0"}))
    assert main(["check", str(tmp_path), "--slot", str(slot_path)]) == 3
    assert "not valid" in capsys.readouterr().err
