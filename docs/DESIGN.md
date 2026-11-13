# Contributor tools: design (draft)

Status: checker and submission CI built, everything else designed only.
Last updated 13 Nov 2026.

This repo will be public. It holds all the public parts in one place: the
tools that run on contributors' machines, the CI that checks submissions,
and the films themselves (slots, spine, entries, scene layers). It does not
hold the private mechanics (caps, votes, reputation, thresholds, render
coordinator) or the player page.

The pipeline is drawn in [PIPELINE.md](PIPELINE.md).

## The one idea: everything is a submission bundle

Whatever the work is (a story beat, six storyboard frames, a prop, a shot's
lighting, a door slam), every tool produces the same thing:

```
submission/
  submission.json   slot id, role, contributor, tool versions, file list with sha256, DCO sign-off
  files...          the work itself, in the format the slot's role requires
```

One Python package, `adhd_core`, knows how to build a bundle, check it and
explain the result. The Blender add-on, the desktop app, a CLI and the
submission CI all call the same checks. That keeps the promise "the same file
always gets the same verdict", and it means a new kind of work is one new
role definition plus its checks, not a new program.

The verdict is a pure function of three things: the bundle, the slot spec
(from `main`), and the `adhd_core` version (from `main`). No network, no
clock, no randomness.

## What each kind of work needs

| Work | Made in | Format in the bundle | Checks | Front end |
|---|---|---|---|---|
| Story beat, shot description, title entry | anywhere | `beat.md` | word count, required fields, slot scope | text box |
| Storyboard | any paint app | PNGs + `boards.json` (frame order, timing) | frame count matches shot list, aspect ratio, size | drop zone |
| Greybox blocking | Blender | USD layer (transforms, camera, timing) | shot length, camera rules, stays in set bounds | Blender add-on |
| Model | Blender (or other DCC) | USD or glTF | tris, scale, fits greybox bounds, texture size, texel density | add-on, or drop zone for other DCCs |
| Material | Blender | material recipe JSON (see spike A) | allowed nodes only, values in range, palette ΔE | add-on only |
| Animation | Blender | USD animation on a library rig (see spike B) | length, rig is from library, no sims | add-on only |
| Lighting | Blender | USD lights or recipe JSON | light budget, render time | add-on only |
| Sound | any DAW | WAV | loudness, sample rate, duration, no voice tag | drop zone |
| Render time | n/a | frames, not a bundle | frame verification (server side) | desktop app, render mode |

Two things fall out of this table:

1. **Blender is where most of the craft work happens**, and some roles
   (materials, animation, lighting) only make sense from inside Blender. So
   the add-on is not a side project. It is the main tool.
2. **Text, images and audio need no special software.** Asking a writer to
   install a desktop app to submit 80 words is a bad trade.

## Recommended shape

One shared core, three front ends sized to the work.

```
crowd-sourced-adhd/
  spec/      JSON Schemas: slot spec, submission.json, check result
  core/      adhd_core (Python 3.11): bundle, checks, CI, CLI
  blender/   Blender extension: claim, open context, live checks, submit   [later]
  app/       desktop app (Tauri): drop zone, status and notes, render mode  [later]
  films/     00 is the sandbox, 01 is Film #1. See films/README.md
  .github/   submission CI, core tests, CODEOWNERS
```

### One repo, four rules

Tools and films share one public repo so they cannot drift apart. That is
safe because of four rules:

1. **Submissions are judged by `main`, never by themselves.** CI checks out
   `main` for the checker and slot specs, and the PR head separately as
   data that is never executed.
2. **A submission PR may only add files inside one entry folder**,
   `films/NN/entries/SLOT-ID/GITHUB_ID/`. `adhd ci` fails anything else. A
   PR could still edit the workflow file to fake a pass, so the GitHub App
   checks scope itself and never merges a PR that touches anything outside
   one entry.
3. **Code owners on everything except entries**, enforced by branch
   protection. Tools, slots, spine, scene and CI need the owner's review.
4. **A licence per folder:** Apache 2.0 at the root, GPL 3.0 or later in
   `blender/`, CC BY 4.0 in `films/`.

### core (`adhd_core`)

- Python 3.11 or newer. Blender 4.2 ships 3.11 and Blender 5.2 ships 3.13,
  and the add-on imports the same code.
- Two layers of checks:
  - **Plain checks** run anywhere with no Blender: word counts, image sizes,
    audio loudness, JSON shape, USD stats via `usd-core`.
  - **Blender checks** need `bpy` and run in a pinned headless Blender:
    bounds against the greybox, node allowlist, preview render time.
- Every failed check returns a plain English fix, not just a code.
  "Your prop is 31,402 triangles. The slot allows 20,000. Try a Decimate
  modifier at 0.6."
- A CLI for power users and CI: `adhd check ./submission`,
  `adhd bundle ./my-files --slot SH-012-light`.

### Blender add-on

- Blender 4.2+ extension format (`blender_manifest.toml`), served from our
  own extension repository URL. Blender then installs and updates it from
  inside Preferences, no zip juggling after the first time.
- Sidebar panel, in this order:
  1. **Sign in** with GitHub (device code flow: shows a code, opens the
     browser).
  2. **Slots**: open and claimable slots for the current phase, filtered to
     the roles you can do. Claim or enter an open call from here.
  3. **Open context**: pulls in what the slot needs to sit next to, read
     only. The shot's greybox, camera, neighbouring assets, a bounds box you
     must fit inside, the palette as swatches.
  4. **Live checks**: the plain and Blender checks as a checklist that
     updates while you work, so nobody finds out about a tri budget at
     submit time.
  5. **Submit**: exports with locked settings (the artist never sees an
     export dialog), builds the bundle, runs the full checks, uploads.
  6. **Notes**: reviewer notes for your open submission, shown in the
     sidebar. A revision resubmits to the same PR.
- Never loads `.blend` files from other people. Context comes in as USD or
  recipe JSON.

### Desktop app (later)

- Tauri, as already decided for the render client. **One app, not two**:
  the render client and the contributor app share sign in, a pinned
  Blender, and the trust story, so they become two tabs of one install.
  - **Contribute**: drop zone for boards, audio, and USD or glTF from other
    DCCs. Runs full checks with the pinned Blender. Shows status and notes
    for everything you have in flight.
  - **Render**: the volunteer render client from the handover (caps, idle
    mode, verified frames).
- The app downloads and manages its own pinned headless Blender, checksum
  verified, for checks and renders. Artists keep authoring in whatever
  Blender version they like, within the add-on's supported range.

### Text and image submissions

Recommendation: a submit form on the player page (GitHub sign in, no
IndieCrew account) for story beats, title entries and storyboards. It posts
the same bundle format to the same backend, and CI runs the same checks.
The form lives in the IndieCrew repo, not here, but it only speaks the
public bundle format defined in `spec/`.

## How a submission travels

1. Client signs in with GitHub device flow and swaps that for a backend
   session.
2. Client builds the bundle and runs checks locally.
3. Binary files upload to R2 by content hash, through presigned URLs from
   the backend. Files already there are skipped, so resubmits are fast.
4. The backend (the private GitHub App) creates a branch adding
   `films/NN/entries/SLOT-ID/GITHUB_ID/` with `submission.json` and any
   text files (`.md`, `.json`, `.usda`, up to 256 KB), then opens the PR.
   Binaries never enter Git.
5. CI (`.github/workflows/check-submission.yml`) runs `adhd ci` from `main`:
   scope, slot, contributor folder, then fetches binaries from
   `$ADHD_BLOB_BASE_URL/<sha256>` and runs the checks. Same verdict as the
   local run, or something is broken.
6. Status and notes flow back to every client through the backend (polling
   is fine to start).

## Hard problems to settle first

Each of these is a short spike before any real building. A and B are
settled; full results and renders are in [spikes/README.md](../spikes/README.md).

**A. Materials: settled, recipes.** Through USD, every node graph collapses
to a bare Principled BSDF, with or without MaterialX (Blender writes
MaterialX but does not read it back). A JSON node recipe rebuilt node by
node renders pixel identical in Eevee. Materials travel as recipes; USD
carries geometry only.

**B. Animation: settled, USD skeletal animation.** A skinned rig round
trips through USD within 0.001 mm per vertex over 48 frames, and so does
the animation alone applied to a fresh copy of the rig. The receiving rig
must use quaternion rotation, and bone names and rest pose must match the
library rig. Still to do: export the animation without the mesh.

**C. Who authors the PR.** If the App pushes branches into the public
repo, Actions on those PRs can read repository secrets, unlike fork PRs. So
either the public repo holds **no secrets at all** (simplest, and already
the plan) or the App pushes to a bot owned fork. Credit is recorded by the
backend and shown with a `Co-authored-by` trailer; the DCO sign-off is the
contributor's, accepted in the client before upload.

**D. Pinned Blender.** Checks and renders must use one exact Blender
version, or verdicts and frames will drift. CI, the desktop app and the
render client pin the same version. The add-on supports a range but sends
its exports to the pinned version for the full check. Recommendation:
pin Blender 5.2 LTS. It is supported for two years, and Eevee renders on
it were bit for bit repeatable in spike A.

## Scene loading (to design later)

Contributors have everything from old laptops to workstations. Anyone who
wants to should be able to load the whole film locally, and everyone else
should get a light version that still shows them where their piece sits.

Starting notes, not decisions:

- **The repo can hold the scene's structure, not its weight.** USD layers
  that place things (transforms, references, cameras, timing) are small
  text files and belong in Git. Meshes and textures go to R2 by content
  hash, as already planned. The add-on reads the layers from the repo and
  downloads only the blobs it needs, cached locally by hash so nothing
  downloads twice.
- **USD already has the parts for this.** Payloads let a stage open with
  heavy data unloaded. Purposes (`proxy`, `render`, `guide`) and variant
  sets let one asset carry a light and a full version side by side.
- **Proxies are generated, not made by hand.** On merge, CI builds a
  bounding box and a decimated proxy with small textures for every asset.
  Contributors never have to think about it.
- **The add-on loads by preference:** scope (this shot, this set, whole
  film) times detail (boxes, proxies, full). Default: full detail for your
  own slot and its neighbours, proxies for everything else in the shot.
- **The add-on reads the stage itself.** Blender imports USD as a one time
  conversion and does not keep a live stage, but Blender 5.2 bundles the
  `pxr` bindings (OpenUSD 26.03). So the add-on can open the stage with
  payloads unloaded, pick a detail level per asset, and build or swap the
  Blender objects itself.

## Build order

Follows the film's phases, so each tool exists just before it is needed.

0. **Spec and core.** Slot spec schema, `submission.json` schema, plain
   checks, CLI. CI needs this before anything else. Spikes A to D.
   *Started 13 Nov 2026:* the three schemas are in `spec/`, and `core/` has
   the bundle checks, story and storyboard checks and the `adhd` CLI, with
   tests. Submission CI (`adhd ci` plus the workflow), the sandbox film
   and the one repo layout followed the same day, then spikes A and B.
   Still to do: sound checks, spikes C and D, a first run on real GitHub.
1. **Spine and Story (phases 1 and 2).** Text and image submissions through
   the web form. No install for anyone.
2. **Greybox (phase 3).** Blender add-on, blocking role only: sign in,
   slots, open context, live checks, submit, notes.
3. **Assets and Look (phase 4).** Add-on gains model, material, animation
   and lighting roles. Desktop app ships with the Contribute tab for non
   Blender files.
4. **Open contributions.** Desktop app gains the Render tab.

## Decided

- 2026-11-13: Story beats, title entries and storyboards are submitted
  through a web form on the player page.
- 2026-11-13: Validators live in this repo.
- 2026-11-13: One public repo for tools and films, named
  `crowd-sourced-adhd`, under the four rules above. Film 00 is a sandbox.
- 2026-11-13: Licence: `blender/` under GPL 3.0 or later (Blender add-ons
  that use `bpy` effectively have to be GPL), everything else under
  Apache 2.0 (patent grant, and compatible with GPL 3).
- 2026-11-13: Materials travel as JSON node recipes, animation as USD
  skeletal animation on library rigs (spikes A and B).

## Open decisions

- Oldest Blender version the add-on supports (4.2 LTS is the floor for the
  extension format), and which version to pin for checks and renders
  (5.2 LTS recommended).
