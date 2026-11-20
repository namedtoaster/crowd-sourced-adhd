# adhd-core

The checks every Crowd-Sourced ADHD submission goes through. The Blender
add-on, the web form, the desktop app and the film repo's CI all run this
same package, so a bundle that passes on your machine passes in CI.

Pure Python 3.11, one pure Python dependency, so it can ship inside Blender.

## Use it

```
adhd bundle ./my-beat --slot BEAT-04.json --crew-no 1000001 --name "Your Name"
adhd check ./my-beat --slot BEAT-04.json
```

`adhd check` exits 0 on pass, 1 on fail, 2 on incomplete (some checks are
not built yet or need Blender), 3 when the slot spec itself is broken.
`--json` prints the result in the `check-result` format from `spec/`.

## What it checks so far

- Every bundle: `submission.json` is valid and for this slot, every file
  matches its hash, nothing unlisted, every output the slot asks for is
  there, nothing outside the slot.
- Story and title: UTF-8, front matter fields, word count.
- Storyboard: `boards.json` lists every frame once, frame count, PNG,
  aspect ratio, width, file size, same size throughout.
- Everything else returns `incomplete` until its checks are built.

## Develop

```
uv venv --python 3.11
uv pip install -e ".[dev]"
.venv/bin/python -m pytest
```
