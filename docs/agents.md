# Skill Router — Agent Integration

## Supported Environments

Skill Router's skill package uses the portable directory format
`skill-router/SKILL.md` with YAML frontmatter containing `name` and
`description`. The routing engine itself is agent-neutral.

| Environment | Project skill directory | User-level directory | Status |
|---|---|---|---|
| Generic `SKILL.md` agents | `.agents/skills/` | `~/.agents/skills/` | Implemented and tested by the installer |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` (manual copy) | Layout addressed; project installer supported |
| DeepSeek Harness | `.dsh/skills/` | `~/.agents/skills/` | Layout addressed; project installer supported |

Claude Code and DeepSeek Harness consume the same `SKILL.md` contract; Skill
Router does not claim an agent-specific plugin or native command integration.

## Agent Root Mappings

```
generic → .agents/skills/
claude  → .claude/skills/
deepseek → .dsh/skills/
```

## Installation Layout

### Project Installation

Project installation writes only inside the selected project:

```bash
python3 install.py --scope project --agent generic --project /path/to/project
python3 install.py --scope project --agent claude --project /path/to/project
python3 install.py --scope project --agent deepseek --project /path/to/project
```

The project layout has higher practical precedence than the same user's global
skill in agent implementations that support both scopes.

### Global Installation

Global installation places the skill at `~/.agents/skills/skill-router/` (or
`~/.claude/skills/skill-router/` with `--agent claude`) and the CLI at
`~/.skill-router/skill.py`:

```bash
python3 install.py --scope global --agent generic
python3 install.py --scope global --agent generic --yes  # non-interactive
```

## Upgrade and Uninstall

```bash
python3 install.py --scope project --upgrade --yes
python3 install.py --scope project --uninstall
```

## Maintenance Contract

When Skill Router bootstraps a repository, it writes a marker-guarded contract
into `agent.md` that binds future agents:

- Every added, modified, or removed skill must be re-registered, re-validated,
  and re-benchmarked.
- `route` → recommend. `ambiguous` → ask the user. `no_route` → handle
  directly or ask.
- Execute only commands the router returned with `validated: true`.
- The router is deterministic. Treat `skill-registry/` as generated — edit
  manifests, rebuild with `sync`.
- The cache invalidates itself on manifest changes; `--no-cache` disables it.

## Host-AI Sanity Check

On every `route` result, the host agent should run a one-line check: does the
selected skill clearly match the user's actual task (object + action)? If the
evidence contradicts the request, ask the user instead of executing.
