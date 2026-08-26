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
