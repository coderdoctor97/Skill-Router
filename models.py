"""
skill_router.models — Skill dataclass and manifest loading.

The canonical implementation lives in skill.py; this module exists so the
router internals can import from a dedicated boundary without circular
dependencies.  External consumers should import Skill and load_manifest from
skill.py (which re-exports them).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_MANIFEST_FIELDS = ("name", "description", "keywords", "aliases",
                            "capabilities", "intents", "commands")


@dataclass
class Skill:
    """In-memory representation of a routable skill."""
    name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    use_when: list[str] = field(default_factory=list)
    not_when: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    intents: dict[str, list[str]] = field(default_factory=dict)
    commands: list[dict] = field(default_factory=list)
    manifest_path: str = ""
    skill_dir: str = ""
    bootstrap_generated: bool = False

    @property
    def command_names(self) -> list[str]:
        return [c["name"] for c in self.commands]


def load_manifest(path: Path) -> Skill:
    """Load and structurally validate one manifest.json into a Skill."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    missing = [k for k in REQUIRED_MANIFEST_FIELDS if k not in data]
    if missing:
        raise ValueError(f"{path}: missing required fields {missing}")
    for key, types in (("description", str), ("keywords", list), ("aliases", list),
                       ("capabilities", list), ("intents", dict), ("commands", list)):
        if not isinstance(data.get(key), types):
            raise ValueError(f"{path}: field '{key}' must be {types.__name__}")

    commands = []
    for cmd in data["commands"]:
        if isinstance(cmd, str):
            cmd = {"name": cmd}
        if not isinstance(cmd, dict) or not cmd.get("name"):
            raise ValueError(f"{path}: command entries need a 'name'")
        commands.append({
            "name": str(cmd["name"]),
            "syntax": str(cmd.get("syntax", "")),
            "description": str(cmd.get("description", "")),
            "keywords": list(cmd.get("keywords", []) or []),
        })
    if not commands:
        raise ValueError(f"{path}: at least one command is required")
    names = [c["name"] for c in commands]
    if len(names) != len(set(names)):
        raise ValueError(f"{path}: duplicate command names {names}")

    return Skill(
        name=str(data["name"]),
        description=str(data["description"]),
        keywords=[str(k) for k in data["keywords"]],
        aliases=[str(a) for a in data["aliases"]],
        capabilities=[str(c) for c in data["capabilities"]],
        use_when=[str(x) for x in data.get("use_when", []) or []],
        not_when=[str(x) for x in data.get("not_when", []) or []],
        objects=[str(x) for x in data.get("objects", []) or []],
        actions=[str(x) for x in data.get("actions", []) or []],
        conflicts_with=[str(x) for x in data.get("conflicts_with", []) or []],
        intents={str(k): [str(p) for p in v] for k, v in data["intents"].items()},
        commands=commands,
        manifest_path=str(path),
        skill_dir=str(path.parent),
        bootstrap_generated=bool(data.get("_bootstrap", {}).get("generated")),
    )


def manifest_fingerprint(path: Path) -> str:
    """Stable fingerprint of a manifest's routing-relevant content."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unreadable"
    keys = ["name", "description", "keywords", "aliases", "capabilities",
            "use_when", "not_when", "objects", "actions", "intents",
            "conflicts_with", "commands"]
    blob = json.dumps({k: data.get(k) for k in keys}, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
