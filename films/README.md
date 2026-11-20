# films

One folder per film. Everything in here is licensed CC BY 4.0, see
[LICENSE](LICENSE). Code elsewhere in the repo has its own licence.

```
films/NN/
  spine/      the frozen creative rules: logline, style guide, palette, camera rules
  slots/      one JSON file per slot (format: spec/slot.schema.json)
  entries/    submissions, one folder per slot per contributor:
              entries/<SLOT-ID>/<crew no>/submission.json + text files
  scene/      merged USD layers that make up the film
```

`films/00` is the sandbox. It works like a real film so you can practise a
submission end to end, but it is never rendered.

## Who changes what

- **Entries** arrive as PRs from the GitHub App. A submission PR may only add
  files inside one entry folder. CI checks it with the checker and slot
  specs from `main`, never the copies in the PR.
- **Slots, spine and scene** change only through the owner's review (see
  `.github/CODEOWNERS`).
- **Binaries never enter Git.** Images, audio and meshes go to storage by
  hash. `submission.json` lists them and CI fetches them before checking.
