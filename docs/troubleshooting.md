# Skill Router — Troubleshooting

## Common Issues

| Symptom | Check |
|---|---|
| `doctor` reports missing metadata | Run `bootstrap --root <repo>` then `sync`. |
| A new skill is not routed | Ensure its folder has `manifest.json`, add routing boundaries, then run `sync`. |
| `validate` reports drift | Do not edit generated JSON; run `sync` after changing a manifest. |
| Install refuses to overwrite | Inspect the displayed destination; use `--upgrade` only for a known Skill Router install. |
| Agent cannot see the skill | Confirm the directory for that agent, restart the session, and use `doctor` for the CLI root. |
| Windows command not found | Use `py install.py` and `py .skill-router\\skill.py ...`. |
| `no_route` for a known skill | The skill's `use_when` triggers may not cover the request phrasing. Check the manifest. |
| `ambiguous` when one skill should win | Overlapping skills may have incomplete or conflicting metadata. Check `use_when`, `not_when`, `objects`, and `actions`. |
| Benchmark shows less than 100% accuracy | Check which cases fail with `--debug` output. Likely a corpus manifest gap. |
| Cache returns stale results | Run `sync` to regenerate the routing manifest (changes fingerprint). Use `--no-cache` to bypass. |

## Diagnosis Commands

```bash
# Full health check
python3 skill.py doctor --root /path/to/repo

# Validate manifests and check for drift
python3 skill.py validate --root /path/to/repo

# Rebuild all generated metadata
python3 skill.py sync --root /path/to/repo

# Debug a specific route
python3 skill.py route "your request" --root /path/to/repo --debug
```

## Performance

If routing feels slow on a large skill library:

1. Verify the cache is enabled (check `CONFIG_ACTIVE` or `--no-cache` is not
   being used).
2. Ensure `max_candidates` is not set too high (default: 20).
3. Check that the routing manifest file exists and is readable — without it,
   the router falls back to reading every manifest on every call.
