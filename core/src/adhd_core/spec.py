"""Loads the JSON Schemas from spec/ and validates documents against them."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any, Callable

import fastjsonschema

SCHEMAS = ("slot", "submission", "check-result")


def _read_schema(name: str) -> dict[str, Any]:
    filename = f"{name}.schema.json"
    packaged = resources.files("adhd_core") / "spec" / filename
    if packaged.is_file():
        return json.loads(packaged.read_text(encoding="utf-8"))
    # Running from a checkout: core/src/adhd_core/spec.py -> repo/spec/
    repo_copy = Path(__file__).resolve().parents[3] / "spec" / filename
    return json.loads(repo_copy.read_text(encoding="utf-8"))


@cache
def _validator(name: str) -> Callable[[Any], Any]:
    schema = dict(_read_schema(name))
    # fastjsonschema speaks draft 7. The schemas only use keywords that mean
    # the same thing in draft 7 and 2020-12, so validate them as draft 7.
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    return fastjsonschema.compile(schema)


def validate(name: str, doc: Any) -> str | None:
    """Returns None when doc is valid, otherwise the first problem found."""
    if name not in SCHEMAS:
        raise ValueError(f"unknown schema {name!r}")
    try:
        _validator(name)(doc)
    except fastjsonschema.JsonSchemaValueException as exc:
        return exc.message.replace("data.", "", 1).replace("data ", "", 1)
    return None


class SlotError(Exception):
    """The slot spec itself is broken. That is the owner's problem, not the contributor's."""


def load_slot(path: Path) -> dict[str, Any]:
    try:
        slot = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SlotError(f"Could not read slot spec {path}: {exc}") from exc
    problem = validate("slot", slot)
    if problem:
        raise SlotError(f"Slot spec {path} is not valid: {problem}")
    return slot
