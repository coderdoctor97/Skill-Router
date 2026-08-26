# Skill Router — Configuration

## Config Reference

All thresholds and weights live in `CONFIG` / `RANK_WEIGHTS` /
`CHEAP_WEIGHTS` at the top of `skill.py`.

### Routing Thresholds (`CONFIG`)

| Key | Default | Description |
|---|---|---|
| `filter_floor` | 0.15 | Minimum cheap score to become a Stage A candidate |
| `max_candidates` | 20 | Maximum candidates passed to Stage B |
| `route_floor` | 0.45 | Minimum confidence to emit a ROUTE decision |
| `no_route_floor` | 0.14 | Below this: NO_ROUTE |
| `ambiguity_gap` | 0.15 | If second-best is within this gap of best: AMBIGUOUS |
| `multi_floor` | 0.33 | Extra skill needs this confidence to join a multi-skill plan |
| `multi_cap` | 3 | Maximum skills in one plan |
| `cache_size` | 256 | Maximum cached route results |
| `use_cache` | true | Enable/disable result caching |

### Stage B Weights (`RANK_WEIGHTS`)

| Dimension | Weight |
|---|---|
| intent | 0.35 |
| object | 0.18 |
| action | 0.16 |
| capability | 0.16 |
| name_alias | 0.16 |
| domain | 0.16 |
| trigger | 0.14 |
| specificity | 0.08 |

### Stage A Weights (`CHEAP_WEIGHTS`)

| Signal | Weight |
|---|---|
| name | 0.60 |
| alias | 0.55 |
| use_when | 0.45 |
| intent | 0.35 |
| keyword | 0.25 |
| capability | 0.20 |
| object | 0.15 |
| action | 0.15 |

### Penalties

| Constant | Value | Description |
|---|---|---|
| `OBJECT_MISMATCH_PENALTY` | 0.25 | Per unmatched concrete-object token |
| `CONFLICT_PENALTY` | 0.30 | Competing same-task conflicting skill |
| `NOT_WHEN_DISQUALIFY_RATIO` | 0.60 | Negative trigger match ratio that disqualifies |
| `EXPLICIT_CALL_BONUS` | 0.45 | Raw bonus when the skill is explicitly named |

### Word Lists

The router maintains several word lists that affect scoring behavior:

- **`CONCRETE_OBJECTS`** (52 words) — nouns that, if mentioned in a request but
  not covered by a skill, trigger an object-mismatch penalty.
- **`GENERIC_WORDS`** (20 words) — low-specificity words; a match on these
  alone does not earn specificity credit.
- **`DOMAIN_WORDS`** (28 words) — domain nouns used to surface genuine
  clusters as AMBIGUOUS instead of dropping them to NO_ROUTE.
- **`STOPWORDS`** (74 words) — filtered out during tokenization.

## Runtime Configuration

Override supported values without editing code by setting
`SKILL_ROUTER_CONFIG` to a JSON file path:

```json
{"route_floor": 0.50, "ambiguity_gap": 0.12, "max_candidates": 20}
```

```bash
SKILL_ROUTER_CONFIG=/path/to/router-config.json python3 skill.py route "..." --root .
```

The environment configuration is process-local and overrides built-in defaults.
Use the same environment variable in the agent process if a project needs an
override. `--no-cache` bypasses the route cache for one request.
