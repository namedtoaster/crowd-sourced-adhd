# spec

The shared formats. Every tool reads or writes these, so they change
carefully: a breaking change bumps the `@0` in the `schema` field.

| File | What it describes | Lives where |
|---|---|---|
| `slot.schema.json` | One slot: role, mode, dependencies, context layers, outputs, role specific limits | Film repo, `slots/<id>.json` |
| `submission.schema.json` | `submission.json` at the root of every bundle | Every bundle |
| `check-result.schema.json` | What the checks return: verdict, each check, plain English fix | Clients and CI output |

`examples/` has one of each, all valid. They use JSON Schema 2020-12.
