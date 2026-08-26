# Skill Router — Development

## Setup

```bash
git clone <repository-url>
cd skill-router
python tests/run_tests.py
```

## Running Tests

```bash
# Full regression suite
python tests/run_tests.py

# Via unittest discovery
python -m unittest discover -s tests -p "test_*.py"
```

## Running Validation

```bash
python skill.py validate --root .
```

## Running Benchmarks

```bash
# In-process
python skill.py benchmark

# External runner (version-agnostic)
python benchmarks/run_benchmark.py --repeat 3
```

## Adding a New Skill

1. Create `skills/<name>/SKILL.md` and `skills/<name>/manifest.json`.
2. The manifest `name` must match the folder name.
3. Fill in `use_when`, `not_when`, `objects`, and `actions` for precise routing.
4. Run `python skill.py sync --root .`
5. Verify with `python skill.py validate --root .`
6. Test with `python skill.py route "<sample request>" --root . --debug`

## Modifying Skill Metadata

- Edit the skill's `manifest.json` directly.
- Do NOT hand-edit files in `skill-registry/` — they are generated.
- After any manifest change, run `sync` and `validate`.

## Routing Behavior Changes

Routing changes are behavioral changes even when APIs don't change. Before
modifying routing logic:

1. Add a regression case in `tests/test_router.py`.
2. Add a gold-set case in `benchmarks/gold-set.json` if the behavior is not
   already covered.
3. Run the full benchmark and confirm no regressions.
4. Include `--debug` output in the PR description.

## Installer Changes

The installer is an important trust surface. Changes to `install.py` must be
covered by `tests/test_install.py`. Regression-test:

- First install
- Repeated install
- Upgrade
- Destination already exists (unrelated file)
- Dry run
- Uninstall

## Coding Expectations

- Keep the router deterministic. No randomness, no network calls, no LLM in
  the hot path.
- Keep agent-specific logic in the installer/layout layer, not the core router.
- Preserve backward compatibility with V1 manifests.
- Run `sync`, `validate`, `tests/run_tests.py`, and `benchmark` before
  submitting a PR.
