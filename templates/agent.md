<!-- Skill_by_Satya:routing-contract -->
# Skill Router & Dynamic Skill Registry (Skill_by_Satya V2)

This repository has a two-stage skill router. `skill.py` reads a compact
generated routing manifest, filters candidates cheaply, ranks the candidate
set semantically, and returns one of three decisions: `route` (recommended
skill + command), `ambiguous` (ask the user), or `no_route` (handle directly).
It may also propose a minimal ordered multi-skill plan. It never executes
anything; you decide and execute.

CLI: `python3 skill.py list | route "<request>" [--debug] | validate | sync | discover | benchmark`

## Host-AI sanity check (mandatory, cheap)
The router proposes; the host AI validates. On every `route` result, run a
one-line check: does the selected skill clearly match the user's actual task
(object + action)? If the evidence contradicts the request, ask the user
instead of executing.

## Maintenance contract (mandatory)
Whenever a skill is installed, added, modified, or removed, you MUST
synchronize the routing environment:

* New skill: inspect it -> create/verify `skills/<name>/manifest.json`
  (name matches the folder; register only commands that actually exist; add
  `use_when`/`not_when`/`objects`/`actions` so the router can distinguish it)
  -> `python3 skill.py sync` -> test with
  `python3 skill.py route "<sample request>" [--debug]`.
* Modified skill: update its manifest -> `sync` -> re-run any affected
  gold-set cases (`python3 skill.py benchmark`).
* Removed skill: delete the folder -> `sync` (registry and routing manifest
  are regenerated; the stale cache is invalidated) -> `validate`.

## Operating rules
* Execute only commands the router returned with `validated: true` — a
  command missing from a discovered manifest is rejected, not run.
* `route` -> recommend. `ambiguous` -> ask the user. `no_route` -> handle
  directly or ask.
* The router is deterministic. Treat `skill-registry/registry.json` and
  `skill-registry/routing-manifest.json` as generated: edit manifests, rebuild
  with `sync`. The cache invalidates itself on manifest changes; `--no-cache`
  disables it.

## Separation of responsibilities
* `agent.md`: behavior, operating rules, this maintenance contract.
* `skills/<name>/manifest.json`: skill identity, capabilities, keywords,
  aliases, intents, commands, and routing boundaries (source of truth).
* `skill-registry/routing-manifest.json`: compact generated routing metadata
  (never hand-edited).
* `skill-registry/registry.json`: generated index (never hand-edited).
* `skill.py`: filtering, ranking, decision, validation, cache.
* You: interpret, sanity-check, decide, ask when ambiguous, execute.

<!-- Skill_by_Satya:routing-contract -->
