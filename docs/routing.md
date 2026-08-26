# Skill Router — Routing

## Two-Stage Pipeline

### Stage A — Cheap Candidate Filtering

Runs over the **entire** library from the compact routing manifest. Each entry
gets scored from deterministic signals with hard weights:

| Signal | Weight |
|---|---|
| Name full-match | 0.60 |
| Alias full-match | 0.55 |
| use_when trigger (≥50% coverage) | 0.45 |
| Intent phrase | 0.35 |
| Keyword full-match | 0.25 |
| Capability | 0.20 |
| Object | 0.15 |
| Action | 0.15 |

Uses `credit_ratio()` for multi-token phrases — a single shared token earns
zero credit (≥2 tokens required). Entries scoring ≥ `filter_floor` (0.15)
become candidates, capped at `max_candidates` (20).

### Stage B — Structured Semantic Ranking

Runs only on the reduced candidate set. Computes 8 weighted dimensions using
`RANK_WEIGHTS`:

| Dimension | Weight | Description |
|---|---|---|
| intent | 0.35 | explicit intent phrase match |
| object | 0.18 | the thing acted on |
| action | 0.16 | what is being done |
| capability | 0.16 | what the skill can do |
| trigger | 0.14 | positive use_when trigger strength |
| name_alias | 0.16 | explicit skill name / alias |
| specificity | 0.08 | long matched phrases → more specific |
| domain | 0.16 | request names a domain the skill covers |

Each dimension is *gated* — it contributes zero unless the `credit_ratio` is
≥ 0.5. The trigger score scales with phrase length
(`min(0.9, ratio * (0.40 + 0.12*(k-1)))`).

### Explicit Call Bonus

If the request literally names the skill (name or full alias match), it gets a
+0.45 raw bonus — but **only if** the skill has at least one strong anchor
(intent, object, or domain score of 1.0). This prevents adversarial traps like
"make my code impeccable" routing to the prose skill `impeccable`.

## Three-Pass Penalty System

### Pass 1 — `not_when` + `_object_mismatch()`

Applied right after raw confidence:

- **`not_when`**: If a negative trigger phrase ≥60% matches the request **and**
  the skill has weak positive anchors (intent+trigger+object+action < 0.15),
  the skill is hard-disqualified (×0.15 multiplier). Otherwise it gets a soft
  penalty (×0.6). This allows mixed requests like "review for complexity AND
  check the endpoint" to keep both candidates for multi-skill planning.

- **`_object_mismatch()`**: Only fires when **all** concrete objects in the
  request are foreign to the skill (not just some). Applies penalty up to 0.5
  per missing concrete object. `not_when` phrases are **deliberately excluded**
  from coverage counting.

### Pass 2 — `conflicts_with`

Only fires when a conflicting skill is a **real competitor** (confidence ≥
max(0.30, best−0.10)) **AND** they overlap on task dimensions (shared
triggers/intents/objects). Applies `CONFLICT_PENALTY` (0.30). Skills with
completely disjoint dimensions are NOT penalized — this enables multi-skill
plans.

## Decision Logic

1. **Try multi-skill plan first** via `try_multi_plan()`: if ≥2 skills match
   disjoint dimensions with confidence ≥ `multi_floor` (0.33), returns an
   ordered plan capped at `multi_cap` (3).
2. **ROUTE**: best confidence ≥ `route_floor` (0.45) AND best − second >
   `ambiguity_gap` (0.15)
3. **AMBIGUOUS**: best confidence ≥ `no_route_floor` (0.14) but gap too small
   — returns up to 4 candidates
4. **NO_ROUTE**: best confidence below `no_route_floor` (0.14) — returns empty

## Multi-Skill Plans

`try_multi_plan` builds a minimal ordered multi-skill plan when ≥2 skills
match disjoint dimensions with sufficient confidence. Ordering uses "then" /
"first" hints and sorts by the position of the first matched object phrase in
the original request.

Task identity dimensions are objects, intents, and triggers — NOT generic
actions like "write". Two skills may both "write" yet handle different objects.

## No-Route Behavior

`_empty_result()` returns: `decision="no_route"`, `status="no_match"`,
`skill=None`, `skills=[]`, `command=None`, `confidence=0.0`,
`evidence="no matching skill"`, `validated=False`, `alternatives=[]`.

Triggered when: (a) tokenized request is empty, (b) no candidates pass Stage A
filtering, or (c) best ranked confidence < `no_route_floor`.

## Command Validation

`resolve_command()` picks the best command by scoring name token overlap (0.55)
+ keyword full-match (0.30). If there's only one command, it's returned
automatically. The result always includes `validated: true` only if the command
name appears in the manifest's declared commands list.
