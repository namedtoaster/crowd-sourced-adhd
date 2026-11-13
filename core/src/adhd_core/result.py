"""Check and Result, and their canonical JSON form."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal["pass", "fail", "skip"]
Verdict = Literal["pass", "fail", "incomplete"]


def canonical_json(doc: Any) -> bytes:
    """One byte sequence per document, so hashes and results are reproducible."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class Check:
    id: str
    status: Status
    message: str
    fix: str | None = None
    measured: Any = None
    limit: Any = None
    where: str | None = None

    def __post_init__(self) -> None:
        if self.status == "fail" and not self.fix:
            raise ValueError(f"check {self.id} failed without a fix")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "status": self.status, "message": self.message}
        for key in ("fix", "measured", "limit", "where"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


@dataclass
class Result:
    core: str
    slot: str
    bundle_sha256: str
    checks: list[Check] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        statuses = {c.status for c in self.checks}
        if "fail" in statuses:
            return "fail"
        if "skip" in statuses or not self.checks:
            return "incomplete"
        return "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "adhd/check-result@0",
            "core": self.core,
            "slot": self.slot,
            "bundle_sha256": self.bundle_sha256,
            "verdict": self.verdict,
            "checks": [c.to_dict() for c in self.checks],
        }

    def to_json(self) -> bytes:
        return canonical_json(self.to_dict())
