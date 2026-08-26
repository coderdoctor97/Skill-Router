# Changelog

All notable changes to Skill Router are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project uses
[semantic versioning](https://semver.org/).

## Unreleased

### Added
- `.github/workflows/tests.yml` — CI test matrix (Python 3.10–3.13)
- `.github/workflows/lint.yml` — CI validation and syntax checks
- `.github/workflows/benchmark.yml` — Benchmark CI on main branch pushes
- `.github/CODEOWNERS` — Code ownership definitions
- `.github/ISSUE_TEMPLATE/bug_report.md` — Bug report template
- `.github/ISSUE_TEMPLATE/feature_request.md` — Feature request template
- `.github/PULL_REQUEST_TEMPLATE.md` — PR checklist
- `SECURITY.md` — Security policy and vulnerability reporting process
- `CODE_OF_CONDUCT.md` — Contributor Covenant Code of Conduct
- `docs/` — Documentation structure (architecture, routing, configuration, agents, benchmarking, troubleshooting, development)
- `benchmark-baseline.json` — Saved baseline for regression detection
- `--save-baseline`, `--baseline`, `--gate` flags to benchmark runner
- `--scaling` mode with preset corpus sizes (16/100/500/1000/5000)
- `ambiguity_recall`, `latency_p95_ms`, `metadata_reduction_pct` metrics
- `pyproject.toml` — Standard Python packaging
- `src/skill_router/__init__.py` — Packaging shim for pip install
- `models.py` — Extracted model layer (Skill, load_manifest)

### Changed
- Branding unified to "Skill Router" throughout public-facing files
- `manifest.json` aliases cleaned up (removed "Skill_by_Satya" alias)
- `CONTRACT_MARKER` updated to `<!-- Skill Router:routing-contract -->`
- `CONTRIBUTING.md` expanded with routing behavior change guidelines
- `.gitignore` expanded with `.coverage`, `htmlcov/`, `.tox/`, `benchmark-results/`, `*.egg-info/`, `dist/`, `build/`, `wheels/`
- Windows path test failure fixed in `test_install.py`
- Benchmark accuracy language scoped to reflect gold-set limitations
- Troubleshooting table entry for benchmark accuracy clarified
- `skill.py` built-in benchmark includes per-case latency and p95 reporting
- Scaling results documented with honest interpretation

### Fixed
- Test failure on Windows due to path separator in `test_install.py`

## [2.0.0] — 2025-01-15

### Added
- Two-stage deterministic routing (cheap filtering + structured ranking)
- Three-way decisions: `route`, `ambiguous`, `no_route`
- Multi-skill plans with disjoint-dimension detection
- Positive and negative routing boundaries (`use_when`, `not_when`)
- Explicit call bonus with anchor requirement (adversarial protection)
- Three-pass penalty system (not_when, object mismatch, conflicts)
- Result caching with fingerprint-based invalidation
- Drift detection between corpus and routing manifest
- Conservative bootstrap for existing or empty repositories
- Validation with exit codes
- Gold-set benchmark (36 cases, 16-skill corpus)
- Global/project installer with agent-specific layouts
- `--version`, `--debug`, `--no-cache` CLI flags
- Host-AI sanity check in maintenance contract

[2.0.0]: https://github.com/coderdoctor97/skill-router/releases/tag/v2.0.0
