# Crowd-Sourced ADHD

A 3D short film made one small piece at a time. Anyone can add a story
beat, a model, a shot's lighting, a sound. Every merge re-renders the cut.
Watch it at indiecrew.co/adhd.

This repo holds everything public: the tools, the checks every submission
goes through, and the films themselves.

| Folder | What | Status |
|---|---|---|
| `films/` | Slots, spine, entries and scene for each film. `00` is a practice sandbox | sandbox ready, Film #1 not started |
| `core/` | `adhd_core`: the checks, plus the `adhd` CLI | story and storyboard checks |
| `spec/` | Shared formats: slot, submission, check result | draft |
| `blender/` | Blender add-on: claim, check as you go, submit without Git | planned |
| `app/` | Desktop app: other files, and donating render time | planned |
| `docs/` | [Design](docs/DESIGN.md) and [pipeline diagram](docs/PIPELINE.md) | |

## Licences

- Code: Apache 2.0, see [LICENSE](LICENSE).
- `blender/`: GPL 3.0 or later, because Blender add-ons have to be.
- `films/`: CC BY 4.0, see [films/LICENSE](films/LICENSE).

Every contribution is signed off under the Developer Certificate of Origin.
