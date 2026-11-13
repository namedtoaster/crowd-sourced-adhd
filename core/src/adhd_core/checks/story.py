"""Story beats and title entries: one markdown file, word capped."""

from __future__ import annotations

from typing import Any

from ..bundle import Bundle
from ..formats import count_words, split_front_matter
from ..result import Check


def check_story(bundle: Bundle, slot: dict[str, Any]) -> list[Check]:
    limits = slot["limits"]
    out: list[Check] = []
    md_outputs = [o["path"] for o in slot["outputs"] if o["kind"] == "markdown"]
    files = [rel for pattern in md_outputs for rel in bundle.files_matching(pattern)]
    if not files:
        return out  # bundle.outputs already failed for this

    for rel in files:
        try:
            text = bundle.read_bytes(rel).decode("utf-8")
        except UnicodeDecodeError:
            out.append(Check("story.format", "fail", f"{rel} is not UTF-8 text.", where=rel,
                             fix="Save it as plain text with UTF-8 encoding."))
            continue
        fm = split_front_matter(text)
        if fm.error:
            out.append(Check("story.format", "fail", fm.error, where=rel,
                             fix='Put "key: value" lines between two --- lines at the very top.'))
            continue
        out.append(Check("story.format", "pass", f"{rel} reads as text.", where=rel))

        required = limits.get("required_fields", [])
        missing = [k for k in required if not fm.fields.get(k)]
        if missing:
            example = "\n".join(f"{k}: ..." for k in required)
            out.append(Check("story.fields", "fail", "Missing or empty: " + ", ".join(missing) + ".", where=rel,
                             fix=f"Start the file with:\n---\n{example}\n---"))
        elif required:
            out.append(Check("story.fields", "pass", "All required fields are filled in.", where=rel))

        words = count_words(fm.body)
        cap = limits["max_words"]
        if words == 0:
            out.append(Check("story.words", "fail", "The beat has no words.", measured=0, limit=cap, where=rel,
                             fix="Write the beat below the front matter."))
        elif words > cap:
            out.append(Check("story.words", "fail", f"{words} words. The slot allows {cap}.", measured=words, limit=cap,
                             where=rel, fix=f"Cut {words - cap} words. Front matter does not count."))
        else:
            out.append(Check("story.words", "pass", f"{words} words. The slot allows {cap}.", measured=words, limit=cap,
                             where=rel))
    return out
