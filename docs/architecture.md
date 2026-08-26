# Skill Router — Architecture

## Overview

Skill Router is a deterministic, two-stage skill routing engine. It reads
compact generated metadata (a routing manifest), filters candidates cheaply,
ranks the reduced candidate set semantically, and returns one of three
decisions: `route`, `ambiguous`, or `no_route`. It may also propose a minimal
ordered multi-skill plan.

The router is a **router, not an executor**. It never runs a returned command.
The host agent receives a structured recommendation, sanity-checks it, and
decides whether to load and execute the selected skill.

## Design Principles

1. **Deterministic.** Same input → same output. Matching logic, scoring order,
   tie-breaking, and output schema are fully inspectable.
2. **Progressive disclosure.** Every request costs compact routing metadata only.
   The selected `SKILL.md` loads after selection.
3. **Agent-neutral core.** Routing logic has no agent-specific branches.
   Agent differences are handled in the installer/layout layer.
4. **Manifests as source of truth.** Generated registry and routing manifest
   are disposable — rebuild with `sync`.
5. **Ambiguity over guessing.** Near-ties return candidates; the agent asks.
6. **Never invent commands.** A command is returned only if a discovered
   manifest declares it.

## Pipeline

```
Request
   ↓ Normalize + stem (once)
   ↓ Stage A — cheap candidate filtering over the whole library
   │     deterministic phrase/keyword/alias signals; 1000 skills → ≤20 candidates
   ↓ Stage B — structured ranking on candidates only
   │     intent · object · action · capability · trigger · name/alias ·
   │     specificity · domain (weighted)
   ↓ Penalties: negative triggers, object mismatch, conflicts
   ↓ Decision: ROUTE / AMBIGUOUS / NO_ROUTE (+ minimal multi-skill plan)
   ↓ Minimal output: decision, skill(s), confidence, command, evidence
   ↓ Host-AI sanity check (one line: does this skill match the task?)
   ↓ Load ONLY the selected SKILL.md
```

## Layer Responsibilities

| Layer | Owns | Stops when |
|---|---|---|
| **Normalizer** | lowercase, tokenize, stem, drop stopwords | input is empty |
| **Stage A — Cheap Filter** | deterministic phrase/alias/keyword signals over the routing manifest; no semantic reasoning | candidates ≤ max_candidates (e.g. 1000 → 20) |
| **Stage B — Semantic Rank** | structured dimensions: intent, object, action, capability, trigger, name/alias, specificity, domain | all candidates scored |
| **Penalties** | negative triggers (not_when), object mismatch, conflicts | skill disqualified or penalized |
| **Decision** | ROUTE (best ≥ floor + clear gap) · AMBIGUOUS (near-tie) · NO_ROUTE (below floor) | decision emitted |
| **Multi-skill plan** | ≥2 candidates ≥ multi floor with disjoint task dimensions; order preserved | plan capped at multi_cap |
| **Cache** | normalized request → decision, keyed by manifest fingerprint | hit (reads nothing) |
| **Host-AI sanity check** | one-line validation of skill vs task | host confirms or asks |
| **Progressive disclosure** | load selected SKILL.md only after routing | task executed |

## Directory Layout

```
agent-repo/
├── agent.md                  ← maintenance contract (behavioral rules)
├── skill.py                  ← two-stage router engine (V2)
├── skill-registry/
│   ├── registry.json         ← generated index (backward compat)
│   └── routing-manifest.json ← compact generated routing metadata
└── skills/<name>/
    ├── SKILL.md
    └── manifest.json         ← source of truth per skill
```

**Sources of truth:** each `manifest.json` and the `skills/` folder (discovery
is a directory scan, never a hardcoded list). Everything in `skill-registry/`
is generated — rebuild with `sync`.

## Invariants

1. The router returns data; it never runs a command.
2. Routing reads compact generated metadata (routing manifest), never full
   skill bodies; skill content loads only after selection.
3. Stage A is deterministic and cheap; stage B is reserved for the reduced
   candidate set.
4. A command is only ever returned if a discovered manifest declares it.
5. Near-ties return `AMBIGUOUS` with the top candidates, never a silent guess.
6. Negative triggers and object mismatches can disqualify or penalize a skill
   even when keywords overlap.
7. Everything is deterministic: same request → same result.
8. The cache is invalidated whenever the routing manifest changes.
