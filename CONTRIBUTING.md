# Contributing

Thanks for helping improve Skill Router. Keep changes focused and preserve the router's agent-neutral core.

## Before opening a pull request

```bash
python3 skill.py sync --root .
python3 skill.py validate --root .
python3 tests/run_tests.py
python3 skill.py benchmark
```

When changing routing behavior, add a regression case and include the relevant `--debug` output in the pull request description. Edit source manifests, not generated registry files.

## Skill metadata

A new skill belongs under `skills/<name>/` in a target agent repository and should contain `SKILL.md` plus `manifest.json`. Use `templates/manifest.json`; provide positive and negative boundaries, objects, and actions so overlapping skills remain safe to route.

## Compatibility

Keep agent-specific paths in the installer/layout layer. Do not add hard-coded home directories, credentials, or machine-specific paths. Document any compatibility claim with a reproducible test.

## Routing Behavior Changes

Routing changes are behavioral changes even when the public API doesn't change. Before modifying routing logic:

1. Add a regression test in `tests/test_router.py`.
2. Add a gold-set case in `benchmarks/gold-set.json` if the behavior is not already covered.
3. Run the full benchmark and confirm no regressions.
4. Include `--debug` output in the PR description.

## Documentation

- Update `README.md` for user-facing changes.
- Update `docs/` for detailed reference changes.
- Update `SKILL.md` if the skill contract changes.
- Run `python3 skill.py validate --root .` to catch manifest issues.

## Installer Changes

The installer is an important trust surface. Changes to `install.py` must be covered by `tests/test_install.py`. Test fresh install, upgrade, dry-run, uninstall, and the safety checks that prevent overwriting unrelated files.
