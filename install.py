#!/usr/bin/env python3
"""Install Skill Router into a project or user skill directory.

The installer is deliberately stdlib-only and conservative: it previews every
path, refuses to overwrite unrelated files, and asks for confirmation before
writing anything unless --yes is supplied.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
PACKAGE_FILES = ("SKILL.md", "manifest.json")

AGENT_ROOTS = {
    "generic": (".agents", "skills"),
    "claude": (".claude", "skills"),
    "deepseek": (".dsh", "skills"),
}


def destination(scope: str, agent: str, project: Path) -> tuple[Path, Path]:
    if scope == "project":
        base = project.joinpath(*AGENT_ROOTS[agent], "skill-router")
        cli = project / ".skill-router" / "skill.py"
    else:
        home = Path.home()
        # ~/.agents is the shared user-level convention. Claude Code also
        # has a native user-level root, which is useful when it is isolated.
        root = (home / ".claude") if agent == "claude" else (home / ".agents")
        base = root / "skills" / "skill-router"
        cli = home / ".skill-router" / "skill.py"
    return base, cli


def plan(scope: str, agent: str, project: Path) -> list[tuple[Path, Path]]:
    skill_dir, cli = destination(scope, agent, project)
    pairs = [(SOURCE / f, skill_dir / f) for f in PACKAGE_FILES]
    pairs.append((SOURCE / "skill.py", cli))
    return pairs


def copy_safely(pairs: list[tuple[Path, Path]], *, upgrade: bool = False,
                uninstall: bool = False) -> list[str]:
    # Preflight every destination first so a conflict cannot leave a partial
    # installation behind.
    if not uninstall:
        for source, target in pairs:
            if target.exists() and not upgrade and target.is_file() \
                    and target.read_bytes() != source.read_bytes():
                raise RuntimeError(f"refusing to overwrite existing file: {target} (use --upgrade)")
    written = []
    for source, target in pairs:
        if uninstall:
            if target.exists():
                target.unlink()
                written.append(str(target))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # Upgrades are explicit. Normal installs never overwrite an
            # unrelated skill or user-authored CLI.
            if target.is_file() and target.read_bytes() == source.read_bytes():
                continue
            if not upgrade:
                raise RuntimeError(f"refusing to overwrite existing file: {target} (use --upgrade)")
        shutil.copy2(source, target)
        if target.name == "skill.py":
            target.chmod(target.stat().st_mode | 0o111)
        written.append(str(target))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Skill Router safely.")
    parser.add_argument("--scope", choices=("global", "project"),
                        help="installation scope; omit to choose interactively")
    parser.add_argument("--agent", choices=tuple(AGENT_ROOTS), default="generic",
                        help="skill layout to target (default: generic .agents/skills)")
    parser.add_argument("--project", type=Path, default=Path.cwd(),
                        help="project root for project installs (default: current directory)")
    parser.add_argument("--yes", action="store_true", help="confirm the displayed plan")
    parser.add_argument("--dry-run", action="store_true", help="show changes without writing")
    parser.add_argument("--upgrade", action="store_true", help="replace files at the Skill Router destinations")
    parser.add_argument("--uninstall", action="store_true", help="remove only the Skill Router files at the destinations")
    args = parser.parse_args(argv)

    scope = args.scope
    if scope is None:
        print("Skill Router installation\n\nWhere should it be installed?\n"
              "  1. Global   user-level, available across projects\n"
              "  2. Project  current project only\n")
        choice = input("Choose [1/2] (default: 1): ").strip() or "1"
        if choice not in ("1", "2"):
            print("error: choose 1 for global or 2 for project", file=sys.stderr)
            return 2
        scope = "global" if choice == "1" else "project"

    project = args.project.resolve()
    if scope == "project" and not project.is_dir():
        print(f"error: project directory does not exist: {project}", file=sys.stderr)
        return 2
    pairs = plan(scope, args.agent, project)
    print(f"\nScope: {scope}\nAgent layout: {args.agent}\nThe following files will be added:")
    for source, target in pairs:
        print(f"  {target}")
    if args.dry_run:
        print("\nDry run: no files changed.")
        return 0
    if not args.yes:
        action = "uninstall" if args.uninstall else ("upgrade" if args.upgrade else "install")
        print(f"This will {action} only the paths listed above.")
        answer = input("\nProceed? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Installation cancelled; no files changed.")
            return 0
    try:
        written = copy_safely(pairs, upgrade=args.upgrade, uninstall=args.uninstall)
    except (OSError, RuntimeError) as exc:
        print(f"error: installation stopped safely: {exc}", file=sys.stderr)
        return 1
    print(f"Installed Skill Router ({len(written)} new files).")
    print("Verify with:")
    print(f"  {pairs[-1][1]} --version")
    if scope == "project":
        print("  # For an existing skill repository, initialize metadata first:")
        print(f"  {pairs[-1][1]} bootstrap --root {project}")
        print(f"  {pairs[-1][1]} doctor --root {project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
