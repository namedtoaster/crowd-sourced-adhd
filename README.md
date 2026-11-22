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

## How AI is and isn't used

**The film is made by people.** Every idea, story beat, drawing, model,
animation and sound in it comes from a person. Generative AI is banned from
anything that ends up in the film: no AI generated images, video, 3D models,
textures, music, sound or writing. If you see an entry that looks AI
generated, please [report it](https://www.indiecrew.co/adhd/report).
Entries found to use it are removed.

**The tools are built with help from AI.** The website, the submission bot
and the checks in this repo are written by the project lead with Claude, an
AI coding assistant. That's the plumbing, not the film. Claude doesn't write
the story, pick entries or make anything that appears on screen. Commits it
helped write are marked as co-authored.

**Some sorting uses machine learning.** To help organise what people send,
for example placing similar ideas near each other on the ideas board, the
site uses machine learning models that measure how alike two pieces of
writing are. They never create anything and never decide what goes in the
film. People do that: the project lead picks during the spine, and the crowd
votes after.

## Licences

- Code: Apache 2.0, see [LICENSE](LICENSE).
- `blender/`: GPL 3.0 or later, because Blender add-ons have to be.
- `films/`: CC BY 4.0, see [films/LICENSE](films/LICENSE).

Every contribution is signed off under the Developer Certificate of Origin.
