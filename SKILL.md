---
name: skill-router
description: A meta-skill that installs and maintains a deterministic two-stage skill router (discovery, routing, command resolution) in an agent repository. Use when the user wants to set up the routing environment, synchronize the registry after skills change, route a request to the right skill and command, or benchmark routing quality.
commands: [bootstrap, sync, discover, list, route, validate, doctor, benchmark]
---

# Skill_by_Satya V2

> A portable meta-skill: install a deterministic two-stage skill router into
> any agent repository, then keep its routing metadata in sync as skills change.

## What it is

A meta-skill about skills: it installs the machinery that makes every other
skill in a repo discoverable and routable, without reading the skill library
on every request. The router reads a **compact generated routing manifest**,
filters candidates cheaply, ranks only the candidate set semantically, and
returns one of three decisions: `route`, `ambiguous`, or `no_route`. It may
also propose a minimal ordered multi-skill plan. The router recommends; the
agent decides, sanity-checks, and executes.

The mission is unchanged from V1: **find the right skill with the least
unnecessary reading, least unnecessary context, least unnecessary latency,
and the smallest acceptable risk of wrong routing.**

## Three decisions

| decision | means | action |
|---|---|---|
| `route` | one skill (or minimal skill set) clearly dominates | recommend it |
| `ambiguous` | candidates too close to pick safely | ask the user |
| `no_route` | nothing sufficiently relevant | handle directly or ask |

A route is never forced on a vague match. Full V1→V2 rationale, benchmark,
and measurements: see [`UPGRADE-REPORT.md`](UPGRADE-REPORT.md).

## Environment

```
Agent
├── agent.md                ← maintenance contract (behavioral rules)
├── skill.py                ← two-stage router engine (V2)
├── skill-registry/
│   ├── registry.json       ← generated index (backward compat)
│   └── routing-manifest.json ← compact generated routing metadata
└── skills/<name>/
    ├── SKILL.md
    └── manifest.json       ← source of truth per skill
```

Sources of truth: each `manifest.json` (identity, capabilities, commands, and
routing boundaries) and the `skills/` folder (discovery is a directory scan,
never a hardcoded list). Everything in `skill-registry/` is generated —
rebuild with `sync`. The cache invalidates itself when the manifest changes
(fingerprint).

## Routing boundaries (per skill manifest)

Every routable skill carries positive and negative boundaries so the router
knows not just what it can do, but why it should win over competitors:

- `use_when` — triggers that indicate the skill should be considered.
- `not_when` — triggers that indicate the skill should NOT be used.
- `objects` / `actions` — the things acted on and the verbs applied, for
  structured matching.
- `conflicts_with` — overlapping skills it competes with on the same task.

## Routing pipeline (two-stage)

```
Request
   ↓ Normalize + stem (once)
   ↓ Stage A — cheap candidate filtering over the whole library
   │     deterministic phrase/keyword/alias signals; 1000 skills → ≤20 candidates
   ↓ Stage B — structured ranking on candidates only
   │     intent · object · action · capability · trigger · name/alias ·
   │     specificity · domain (weighted; see CONFIG in skill.py)
   ↓ Penalties: negative triggers, object mismatch, conflicts
   ↓ Decision: ROUTE / AMBIGUOUS / NO_ROUTE (+ minimal multi-skill plan)
   ↓ Minimal output: decision, skill(s), confidence, command, evidence,
   │   top alternative  (--debug adds the full score breakdown)
   ↓ Host-AI sanity check (one line: does this skill match the task?)
   ↓ Load ONLY the selected SKILL.md
```

**Progressive disclosure:** every request costs compact routing metadata only;
the selected `SKILL.md` loads after selection; references and scripts load
only when the task needs them. The full corpus is never read for routing.

## Commands

Full syntax and descriptions live in `manifest.json` (their single source of
truth):

| command | does |
|---|---|
| `bootstrap` | establish the routing environment (both situations) |
| `sync` | rebuild registry + routing manifest, validate, report orphans (idempotent) |
| `discover` | rebuild registry + routing manifest |
| `list` | print routable skills and their commands |
| `route "<request>" [--debug] [--no-cache]` | recommend the best skill / minimal skill set |
| `validate` | check manifests, registry, and corpus↔manifest drift; exit 0/1 |
| `benchmark` | run the gold-set benchmark in-process |

`route` returns minimal JSON by default. `--debug` adds the normalized
tokens, candidate score breakdown, penalties, and the manifest fingerprint.

## Bootstrap

`python3 skill.py bootstrap [--root DIR]` covers both situations:

- **Skills already exist** — inspects every folder, generates candidate
  manifests for any that lack one (flagged `needs_review`), builds registry
  and routing manifest, appends the agent.md contract, installs skill.py.
- **No skills yet** — creates `skills/`, the registry mechanism, skill.py,
  and the contract; fully operational with zero skills.

Idempotent and conservative: a second run changes nothing.

**Done when** `validate` exits 0, `list` shows the skills, and a smoke
`route "<sample request>" --debug` returns `route` with sensible evidence.

A bootstrap-generated candidate manifest is a starting point, not a final
routing definition: it carries `needs_review: true` until the agent fills in
`use_when` / `not_when` / `objects` / `actions` (validation warns about
missing boundaries). Reviewed manifests are what make routing precise.

## Maintenance contract

Bootstrap writes a marker-guarded contract into `agent.md` that binds future
agents: every added, modified, or removed skill is re-registered, re-validated,
and re-benchmarked against the gold set. The contract, not the router, drives
evolution.

## Config

All thresholds and weights live in `CONFIG` / `RANK_WEIGHTS` /
`CHEAP_WEIGHTS` at the top of `skill.py` — route floor, ambiguity gap,
no-route floor, multi-skill floor, candidate cap, weights per dimension.
Override at runtime with a JSON file via the `SKILL_ROUTER_CONFIG` env var.

## Benchmark and tests

- `benchmarks/gold-set.json` — 36 realistic prompts: positive, near-neighbor,
  ambiguous, no-route, multi-skill, adversarial. Every routing change is
  measured against it (never tune on one example in isolation).
- `benchmarks/run_benchmark.py` — version-agnostic runner (V1 vs V2
  comparison, latency, token/metadata cost, cache).
- `tests/` — regression suite; run `python3 tests/run_tests.py`.
- `benchmarks/corpus/` — 16 overlapping skills used as fixtures.

## Boundaries

- Recommend; the agent decides, sanity-checks, and executes.
- Return only commands a discovered manifest declares.
- Read compact routing metadata; load full skill bodies only after selection.
- Discover from disk on every sync; a new folder + manifest is all a skill needs.
- Treat registry artifacts as derived; edit manifests, rebuild with `sync`.
- Return `ambiguous` with candidates on near-ties; ask rather than guess.
- Cache results keyed on the normalized request; invalidate on manifest change.
- Bootstrap discovers or templates everything; assume nothing about the target repo.

## Reference

- `UPGRADE-REPORT.md` — V1→V2 architecture comparison, benchmark results,
  token/latency measurements, limitations, usage.
- `documentions.md` — build history, failures, and lessons (read it before
  modifying the router).
- `examples/sample-router/README.md` — layer responsibilities, pseudocode,
  invariants.
- `benchmarks/` — gold set, corpus, benchmark runner.
- `tests/` — regression suite.
