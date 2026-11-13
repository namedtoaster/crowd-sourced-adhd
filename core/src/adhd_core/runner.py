"""check_bundle: the one entry point every client and CI calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .bundle import load_bundle
from .checks import ROLE_CHECKS
from .checks.common import check_files, check_manifest, check_outputs
from .result import Check, Result


def check_bundle(bundle_dir: Path, slot: dict[str, Any]) -> Result:
    """Runs every check that applies. Never raises for a contributor's mistake.

    The slot must already be valid (see spec.load_slot).
    """
    from . import __version__

    bundle = load_bundle(Path(bundle_dir))
    result = Result(core=__version__, slot=slot["id"], bundle_sha256=bundle.sha256)

    result.checks += check_manifest(bundle, slot)
    if any(c.status == "fail" for c in result.checks):
        return result  # wrong or unreadable manifest: nothing below means anything

    file_checks = check_files(bundle)
    result.checks += file_checks
    if any(c.id == "bundle.files" and c.status == "fail" for c in file_checks):
        return result  # files do not match their hashes: do not judge them

    result.checks += check_outputs(bundle, slot)

    role_check = ROLE_CHECKS.get(slot["role"])
    if role_check is None:
        result.checks.append(Check("role.checks", "skip",
                                   f"Checks for {slot['role']} are not built yet, so this bundle cannot pass yet."))
    else:
        result.checks += role_check(bundle, slot)
    return result
