"""Tiny readers for the file formats the plain checks need.

Written by hand so the package stays pure Python and every reading is exact.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class PngInfo:
    width: int
    height: int


def read_png_header(data: bytes) -> PngInfo | None:
    """Width and height from the IHDR chunk, or None if this is not a PNG."""
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    if width == 0 or height == 0:
        return None
    return PngInfo(width, height)


_KEY = re.compile(r"^([a-z][a-z0-9_]*):(.*)$")


@dataclass(frozen=True)
class FrontMatter:
    fields: dict[str, str]
    body: str
    present: bool
    error: str | None = None


def split_front_matter(text: str) -> FrontMatter:
    """Flat key: value lines between two --- lines at the top of the file.

    Deliberately not YAML. Keys are lower case, values are plain strings.
    """
    text = text.replace("\r\n", "\n").lstrip("﻿")
    if not text.startswith("---\n"):
        return FrontMatter({}, text, False)
    end = text.find("\n---", 3)
    if end == -1 or text[end + 4 : end + 5] not in ("", "\n"):
        return FrontMatter({}, text, True, "The front matter starts with --- but never closes. Add a second --- line.")
    fields: dict[str, str] = {}
    for n, line in enumerate(text[4:end].split("\n"), start=2):
        if not line.strip():
            continue
        m = _KEY.match(line)
        if not m:
            return FrontMatter({}, text, True, f'Line {n} of the front matter is not "key: value".')
        fields[m.group(1)] = m.group(2).strip()
    return FrontMatter(fields, text[end + 5 :], True)


# A word is a run of letters or digits, joined by apostrophes or hyphens:
# "don't", "half-lit" and "SH-012" are one word each. Markdown symbols are not words.
_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")


def count_words(text: str) -> int:
    return len(_WORD.findall(text))
