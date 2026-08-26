# Skill Router — Benchmarking

## Benchmark Suite

The benchmark suite evaluates routing quality against a gold set of test cases
and reports accuracy, latency, and efficiency metrics.

## Running the Benchmark

```bash
# In-process benchmark (fast)
python3 skill.py benchmark

# External benchmark runner (version-agnostic)
python3 benchmarks/run_benchmark.py

# With repeat for stability
python3 benchmarks/run_benchmark.py --repeat 3

# With stress (duplicate corpus for scaling)
python3 benchmarks/run_benchmark.py --stress 5

# Save results to JSON
python3 benchmarks/run_benchmark.py --json results/benchmark.json
```

## Gold Set

The gold set (`benchmarks/gold-set.json`) contains 36 cases:

| Category | Cases | IDs |
|---|---|---|
| Positive routing | 14 | pos-01 through pos-14 |
| Near-neighbor disambiguation | 8 | nn-01 through nn-08 |
| Ambiguous | 4 | amb-01 through amb-04 |
| No-route | 3 | nr-01 through nr-03 |
| Multi-skill | 3 | ms-01 through ms-03 |
| Adversarial | 4 | adv-01 through adv-04 |

## Metrics

| Metric | Description |
|---|---|
| `decision_accuracy` | Fraction of correct route/ambiguous/no_route decisions |
| `top1_accuracy` | Correct skill in top position (route-only) |
| `top3_recall` | Expected skill appears in top 3 candidates |
| `false_route_rate` | Routed when should be ambiguous/no_route |
| `false_no_route_rate` | Returned no_route when should have routed |
| `ambiguity_precision` | Ambiguous cases where correct skills surfaced |
| `multi_skill_correctness` | Ordered/unordered multi-skill accuracy |
| `avg_latency_ms` | Mean routing latency |
| `avg_output_bytes` | Mean serialized output size |
| `avg_metadata_bytes_per_route` | Mean metadata bytes consumed |
| `cache_hit_rate` | Cache efficiency |

## Benchmark Corpus

The benchmark uses a corpus of 16 overlapping skills under
`benchmarks/corpus/skills/`. The corpus can be regenerated with
`benchmarks/corpus/_generate.py`.

## Scaling

The benchmark runner supports `--stress N` which duplicates the corpus N times
to test behavior at larger skill library sizes. The important measurements at
scale are latency, metadata loaded, candidate count, and routing consistency.

## Reproducibility

To reproduce results:

1. Clone the repository.
2. Ensure Python 3.10+ is installed.
3. Run `python3 skill.py benchmark` from the repository root.
4. For external validation, run `python3 benchmarks/run_benchmark.py`.

Results are deterministic given the same corpus and gold set. Latency
measurements include Python process overhead; actual routing time is a subset.

## Known Limitations

- The 36-case gold set covers 16 skills with deliberately overlapping domains.
  It is a reference suite, not an exhaustive evaluation of production routing
  accuracy across arbitrary skill libraries.
- Benchmark accuracy reflects the quality of skill manifests. Poorly authored
  manifests reduce routing precision but do not introduce security
  vulnerabilities.
- Adversarial cases are synthetic and targeted. Real-world adversarial inputs
  may differ.
