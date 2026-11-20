"""adhd: check a bundle, or make one from a folder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import os

from . import __version__
from .bundle import MANIFEST, build_manifest
from .ci import run_ci, summary_markdown
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


def cmd_ci(args: argparse.Namespace) -> int:
    changed = Path(args.changed).read_text(encoding="utf-8").splitlines()
    base_url = args.blob_base_url or os.environ.get("ADHD_BLOB_BASE_URL") or None
    result = run_ci(args.trusted, args.pr, changed, base_url)
    _print_human(result.to_dict())
    if args.json_out:
        Path(args.json_out).write_bytes(result.to_json() + b"\n")
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(summary_markdown(result))
    return EXIT[result.verdict]


def cmd_bundle(args: argparse.Namespace) -> int:
    slot = load_slot(args.slot)
    root = Path(args.folder)
    if not root.is_dir():
        print(f"{root} is not a folder.", file=sys.stderr)
        return EXIT_USAGE
    manifest = build_manifest(
        root, slot,
        crew_no=args.crew_no, display_name=args.display_name, signed_off_by=args.display_name,
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

    p = sub.add_parser("ci", help="Check a submission PR. Run from the trusted checkout of main.")
    p.add_argument("--trusted", type=Path, required=True, help="Checkout of main: slots come from here.")
    p.add_argument("--pr", type=Path, required=True, help="Checkout of the PR head: read as data only.")
    p.add_argument("--changed", type=Path, required=True, help="File listing the PR's changed paths, one per line.")
    p.add_argument("--blob-base-url", help="Where to fetch files by hash. Defaults to $ADHD_BLOB_BASE_URL.")
    p.add_argument("--json-out", type=Path, help="Also write the result JSON here.")
    p.add_argument("--summary", help="Append a markdown report here (pass $GITHUB_STEP_SUMMARY).")
    p.set_defaults(func=cmd_ci)

    p = sub.add_parser("bundle", help="Write submission.json for a folder.")
    p.add_argument("folder", type=Path)
    p.add_argument("--slot", type=Path, required=True)
    p.add_argument("--crew-no", type=int, required=True, help="Your public crew number.")
    p.add_argument("--display-name", required=True, help="The public name you chose. Shown in credits and used to sign the DCO.")
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
