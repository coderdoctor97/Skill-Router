# Sample Router — architectural reference (V2)

This is a *representative* sketch of the V2 routing architecture, not a copy
of any specific repository's implementation. Use it to communicate the design
or as a starting skeleton for a router written in a different language/stack.

The V2 pipeline itself is defined once in
[`SKILL.md`](../../SKILL.md#routing-pipeline-two-stage). This file covers the
layer responsibilities, a pseudocode skeleton, and the invariants any V2
implementation must hold.

## Pipeline

```
User Request
   ↓ Normalize + stem
   ↓ Stage A — Cheap Pre-Routing (whole library, deterministic)
   ↓ Candidate Filtering (≤ max_candidates)
   ↓ Stage B — Semantic Ranking (candidates only)
   ↓ Confidence / Ambiguity Decision (ROUTE | AMBIGUOUS | NO_ROUTE)
   ↓ Minimal Multi-Skill Plan (disjoint dimensions, optional)
   ↓ Host-AI Sanity Check (router proposes, host validates)
   ↓ Load ONLY Required Skill(s)
   ↓ Execute Task
```

## Layer responsibilities

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

## Minimal skeleton (pseudocode)

```python
def route(request, routing_manifest):
    tokens = normalize(request)                    # Normalizer
    if not tokens: return no_route()
    fingerprint = fingerprint(routing_manifest)    # cache invalidation key
    if cache_hit(tokens, fingerprint): return cached

    candidates = []                                # 1 Stage A (whole library)
    for entry in routing_manifest.skills:
        if cheap_score(tokens, entry) >= FILTER_FLOOR:
            candidates.append(entry)
    candidates = candidates[:MAX_CANDIDATES]

    ranked = []
    for entry in candidates:                       # 2 Stage B (candidates only)
        score = rank(tokens, entry)                #    intent/object/action/...
        score = apply_penalties(score, entry, tokens)  # not_when/mismatch/conflict
        ranked.append((score, entry))
    ranked.sort(desc)

    plan = multi_plan(ranked)                      # 3 disjoint-dimension plan
    if plan: return route(plan)
    best, second = ranked[0], ranked[1] or 0
    if best >= ROUTE_FLOOR and best - second > AMBIGUITY_GAP:
        return route(best)                         # 4 ROUTE
    if best >= NO_ROUTE_FLOOR:
        return ambiguous(ranked)                   #    AMBIGUOUS — ask the user
    return no_route()                              #    NO_ROUTE
```

## Invariants the sample encodes

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
