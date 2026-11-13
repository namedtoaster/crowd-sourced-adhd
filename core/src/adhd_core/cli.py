"""adhd: check a bundle, or make one from a folder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .bundle import MANIFEST, build_manifest
from .runner import check_bundle
from .spec import SlotError, load_slot, validate

EXIT = {"pass": 0, "fail": 1, "incomplete": 2}
EXIT_USAGE = 3


def _print_human(result_dict: dict) -> None:
    print(f"{result_dict['slot']}  {result_dict['verdict'].upper()}")
    width = max((len(c["id"]) for c in result_dict["checks"]), default=0)
    for c in result_dict["checks"]:
        label = {"pass": "ok  ", "fail": "FAIL", "skip": "skip"}[c["status"]]
        print(f"  {label}  {c['id'].ljust(width)}  {c['message']}")
        if c.get("fix"):
            pad = " " * (width + 10)
            for n, line in enumerate(c["fix"].split("\n")):
                print(f"{pad}{'fix: ' if n == 0 else '     '}{line}")


def cmd_check(args: argparse.Namespace) -> int:
    slot = load_slot(args.slot)
    result = check_bundle(args.bundle, slot)
    if args.json:
        sys.stdout.buffer.write(result.to_json() + b"\n")
    else:
        _print_human(result.to_dict())
    return EXIT[result.verdict]


def cmd_bundle(args: argparse.Namespace) -> int:
    slot = load_slot(args.slot)
    root = Path(args.folder)
    if not root.is_dir():
        print(f"{root} is not a folder.", file=sys.stderr)
        return EXIT_USAGE
    manifest = build_manifest(
        root, slot,
        github_id=args.github_id, github_login=args.github_login, signed_off_by=args.sign_off,
        client=f"adhd-cli {__version__}", core=__version__,
        revision=args.revision, message=args.message,
    )
    problem = validate("submission", manifest)
    if problem:
        print(f"Could not make a valid {MANIFEST}: {problem}", file=sys.stderr)
        return EXIT_USAGE
    (root / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {root / MANIFEST} with {len(manifest['files'])} files. Run adhd check next.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adhd", description="Crowd-Sourced ADHD submission tools.")
    parser.add_argument("--version", action="version", version=f"adhd-core {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="Check a bundle against its slot.")
    p.add_argument("bundle", type=Path, help="Folder with submission.json in it.")
    p.add_argument("--slot", type=Path, required=True, help="Slot spec JSON from the film repo.")
    p.add_argument("--json", action="store_true", help="Print the result as canonical JSON.")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("bundle", help="Write submission.json for a folder.")
    p.add_argument("folder", type=Path)
    p.add_argument("--slot", type=Path, required=True)
    p.add_argument("--github-id", type=int, required=True)
    p.add_argument("--github-login", required=True)
    p.add_argument("--sign-off", required=True, help='DCO sign off, "Your Name <you@example.com>".')
    p.add_argument("--revision", type=int, default=1)
    p.add_argument("--message")
    p.set_defaults(func=cmd_bundle)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SlotError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
