# Security Policy

## Supported Versions

Skill Router follows semantic versioning. The following versions receive
security fixes:

| Version | Supported          |
|---------|-------------------|
| 2.x     | Yes               |
| < 2.0   | No                |

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities.

Report security issues privately by email to the maintainer. Include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (a minimal `route` command or installation scenario).
- The Skill Router version (`python3 skill.py --version`), Python version,
  and operating system.
- Any suggested fix or mitigation, if you have one.

The maintainer will acknowledge receipt within 5 business days and provide a
response within 30 days.

## Responsible Disclosure

We ask that you give us a reasonable amount of time to fix the issue before
public disclosure. Please do not share details of the vulnerability with
third parties until a patch is available.

## Security Boundary

Skill Router is a **router, not an executor**. It recommends a skill and
command based on deterministic matching of a compact routing manifest. It
does not execute routed commands, write to arbitrary files, or access
network resources.

Key boundaries:

- **No execution.** The router never runs a returned command. The host
  agent or execution environment is responsible for all command execution.
- **Trusted input.** Installation and routing behavior depend on the skill
  manifests on disk. Malicious or compromised manifests can influence routing
  decisions. Validate manifests before adding new skill sources.
- **Filesystem scoping.** The installer writes only to documented destination
  paths within the chosen scope (project or user home). It refuses to
  overwrite existing files unless `--upgrade` is explicit.
- **Host agent responsibility.** The host agent must sanity-check every
  `route` result before loading or executing a skill. This is the
  Host-AI Sanity Check documented in the maintenance contract.

## Known Limitations

- Routing decisions reflect the quality of skill manifests. Poorly written
  manifests (missing `use_when`, `not_when`, `objects`, `actions`) reduce
  routing precision but do not introduce security vulnerabilities beyond
  incorrect skill selection.
- The benchmark corpus is a reference suite, not an exhaustive security audit.
  Do not rely on benchmark accuracy as a security guarantee.
- The installer does not verify the integrity or provenance of skill source
  files. Only install from trusted repositories.
