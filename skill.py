#!/usr/bin/env python3
"""
skill.py — Skill Router V2 Portable Skill Router

V2 routing mission (unchanged from V1): given a large installed skill library,
identify the most appropriate skill(s) for a user's request WITHOUT reading the
whole library or loading unnecessary skill content on every request.

What changed from V1 (see UPGRADE-REPORT.md for the full comparison):

  * Compact generated routing manifest (skill-registry/routing-manifest.json):
    routing reads ONLY this, never every manifest.json.
  * Two-stage routing: cheap deterministic candidate filtering (stage A) over
    the whole library, then structured semantic ranking (stage B) over only the
    reduced candidate set.
  * Structured score dimensions: intent, object, action, capability, positive
    trigger strength, name/alias, specificity.
  * Positive (use_when) and negative (not_when) routing boundaries per skill;
    conflicts_with disambiguation; object-mismatch rejection.
  * Explicit decisions: ROUTE / AMBIGUOUS / NO_ROUTE, with configurable
    thresholds. Plus minimal multi-skill plans (minimal ordered skill set).
  * Result caching keyed on the normalized request, invalidated when the
    routing manifest changes (fingerprint).
  * Minimal default output + `--debug` mode with a full score breakdown.
  * Host-AI sanity check: the router proposes (skill + compact evidence +
    top alternative); the host AI validates with a one-line check.
  * Gold-set benchmark (`python3 skill.py benchmark`) + regression tests
    (tests/) + drift validation between corpus and routing manifest.

Backward compatible: the V1 CLI (bootstrap/sync/discover/list/route/validate)
and the V1 result fields (status/skill/command/confidence/validated/...) are
preserved; V1 manifests (without use_when/not_when/objects/actions) still load
and route.

CLI:
    python3 skill.py bootstrap [--root DIR] [--force]
    python3 skill.py sync [--root DIR]
    python3 skill.py discover [--root DIR]
    python3 skill.py list [--root DIR]
    python3 skill.py route "<request>" [--root DIR] [--debug] [--no-cache]
    python3 skill.py validate [--root DIR]
    python3 skill.py benchmark [--gold PATH] [--root DIR]
    python3 skill.py stats
    python3 skill.py doctor [--root DIR]
    python3 skill.py --version

Default ROOT is the directory containing this file. All thresholds and weights
live in CONFIG / RANK_WEIGHTS / CHEAP_WEIGHTS below and can be overridden with
a JSON file pointed to by the SKILL_ROUTER_CONFIG environment variable.

The router NEVER executes commands. It only recommends; the agent decides.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Import model layer (extracted to models.py; kept here as aliases for
# backward compatibility with any external imports).
from models import (  # noqa: E402
    REQUIRED_MANIFEST_FIELDS,
    Skill,
    load_manifest,
    manifest_fingerprint,
)

VERSION = "2.0.0"

DEFAULT_ROOT = Path(__file__).resolve().parent

SKILLS_DIR_NAME = "skills"
REGISTRY_DIR_NAME = "skill-registry"
REGISTRY_FILENAME = "registry.json"
ROUTING_MANIFEST_FILENAME = "routing-manifest.json"
MANIFEST_FILENAME = "manifest.json"
SKILL_FILENAME = "SKILL.md"
AGENT_MD_FILENAME = "agent.md"
ROUTER_FILENAME = "skill.py"
CACHE_FILENAME = ".route-cache.json"

REGISTRY_SCHEMA_VERSION = 1
ROUTING_MANIFEST_SCHEMA_VERSION = 2

CONTRACT_MARKER = "<!-- Skill Router:routing-contract -->"

# --------------------------------------------------------------------------
# Config (configurable; override with SKILL_ROUTER_CONFIG=<path-to-json>)
# --------------------------------------------------------------------------
CONFIG = {
    # Stage A (cheap candidate filtering)
    "filter_floor": 0.15,      # cheap score needed to become a candidate
    "max_candidates": 20,      # cap on the candidate set (1000 skills -> ~20)
    # Stage B (decision thresholds)
    "route_floor": 0.45,       # min confidence to ROUTE (with a clear gap)
    "no_route_floor": 0.14,    # below this: NO_ROUTE
    "ambiguity_gap": 0.15,     # second within gap of best -> AMBIGUOUS
    # Multi-skill plans
    "multi_floor": 0.33,       # extra skill needs this confidence to join
    "multi_cap": 3,            # max skills in one plan
    # Cache
    "cache_size": 256,
    "use_cache": True,
}

# Stage B structured dimensions (normalized by their sum).
RANK_WEIGHTS = {
    "intent": 0.35,      # explicit intent phrase match
    "object": 0.18,      # the thing acted on
    "action": 0.16,      # what is being done
    "capability": 0.16,  # what the skill can do
    "trigger": 0.14,     # positive use_when trigger strength
    "name_alias": 0.16,  # explicit skill name / alias
    "specificity": 0.08,  # long matched phrases -> more specific
    "domain": 0.16,      # request names a domain the skill covers
}

# Stage A cheap signals (never semantically ranked; just gate candidates).
CHEAP_WEIGHTS = {
    "name": 0.60, "alias": 0.55, "use_when": 0.45, "intent": 0.35,
    "keyword": 0.25, "capability": 0.20, "object": 0.15, "action": 0.15,
}

# Penalties applied after weighting.
OBJECT_MISMATCH_PENALTY = 0.25   # per unmatched concrete-object token
CONFLICT_PENALTY = 0.30          # competing same-task conflicting skill
NOT_WHEN_DISQUALIFY_RATIO = 0.6  # negative trigger match ratio that disqualifies
EXPLICIT_CALL_BONUS = 0.45       # raw bonus when the skill is explicitly named
                                 # (name/alias) and has a supporting anchor

# Concrete object nouns: if a request names one of these and the skill does
# not cover it, the skill is penalized (rejects bag-of-words false routes).
CONCRETE_OBJECTS = frozenset(
    "code api backend frontend ui css chart dashboard database server browser "
    "landing marketing academic paper thesis config build endpoint component "
    "app website readme docs product ad essay email chapter book report form "
    "site graph data diff pr function service microservice schema".split()
)

# Generic words that carry no specificity (a match on these alone is broad).
GENERIC_WORDS = frozenset(
    "review check make help fix improve write text thing stuff work good new "
    "big small code app web page project repo document".split()
)

# Domain nouns: when a request names one of these, every skill whose metadata
# covers it gets domain credit (used to surface genuine clusters as AMBIGUOUS
# instead of dropping them to NO_ROUTE).
DOMAIN_WORDS = frozenset(
    "frontend backend ui css text writing code api marketing docs chart "
    "browser app website dashboard thesis academic chapter essay copy "
    "email prose paper report readme".split()
)

STOPWORDS = frozenset(
    "a an the this that these those with for on of to in at by my your me us "
    "is are was were do does did it its and or but not please can could would "
    "should help i we they he she something some any using use used up out "
    "over under from about into than then there here what which who whom "
    "also then first after".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _load_config() -> dict:
    cfg = dict(CONFIG)
    env = os.environ.get("SKILL_ROUTER_CONFIG")
    if env:
        try:
            overrides = json.loads(Path(env).read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in overrides.items() if k in CONFIG})
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


CONFIG_ACTIVE = _load_config()


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------
def stem(word: str) -> str:
    """Light deterministic stemmer: plural/verb endings only. Both sides of a
    match are stemmed, so the transformation is safe."""
    if len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and word.endswith(("ches", "shes", "xes", "zes", "ses")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {stem(t) for t in _TOKEN_RE.findall(text.lower()) if t not in STOPWORDS}


def normalize(text: str) -> str:
    return " ".join(sorted(tokens(text)))


_PHRASE_TOKENS_CACHE: dict[str, frozenset] = {}


def phrase_tokens(phrase: str) -> frozenset:
    """Token set for a metadata phrase, memoized per process (phrases repeat
    across requests, so tokenizing them every route is pure waste)."""
    cached = _PHRASE_TOKENS_CACHE.get(phrase)
    if cached is not None:
        return cached
    ts = frozenset(tokens(phrase))
    _PHRASE_TOKENS_CACHE[phrase] = ts
    return ts


def phrase_ratio(req: set[str], phrase: str) -> float:
    """Fraction of the phrase's tokens present in the request (0..1)."""
    pt = phrase_tokens(phrase)
    if not pt:
        return 0.0
    return len(pt & req) / len(pt)


def credit_ratio(req: set[str], phrase: str) -> float:
    """Like phrase_ratio, but a multi-token phrase needs >=2 tokens present to
    earn any partial credit. A single shared token ('component', 'review') is
    too weak a signal to score."""
    pt = phrase_tokens(phrase)
    if not pt:
        return 0.0
    matched = len(pt & req)
    if len(pt) >= 2 and matched <= 1:
        return 0.0
    return matched / len(pt)


def phrase_full(req: set[str], phrase: str) -> bool:
    pt = phrase_tokens(phrase)
    return bool(pt) and pt <= req


def round3(x: float) -> float:
    return round(x, 3)


# --------------------------------------------------------------------------
# Stats (for benchmark + debugging)
# --------------------------------------------------------------------------
_STATS = {"routes": 0, "cache_hits": 0, "cache_misses": 0,
          "metadata_bytes_loaded": 0.0, "fallback_manifest_bytes": 0.0}


def reset_stats() -> None:
    for k in _STATS:
        _STATS[k] = 0.0 if "bytes" in k else 0


def get_stats() -> dict:
    return dict(_STATS)


def skill_folders(root: Path | None = None) -> list[Path]:
    skills_dir = (root or DEFAULT_ROOT) / SKILLS_DIR_NAME
    if not skills_dir.is_dir():
        return []
    return sorted(p for p in skills_dir.iterdir() if p.is_dir())


def discover_skills(root: Path | None = None) -> list[Skill]:
    """Discover every routable skill under <root>/skills (used by sync,
    validate, bootstrap — NOT by hot-path routing)."""
    skills_dir = (root or DEFAULT_ROOT) / SKILLS_DIR_NAME
    found: list[Skill] = []
    if not skills_dir.is_dir():
        return found
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        manifest = entry / MANIFEST_FILENAME
        if not manifest.is_file():
            continue
        try:
            found.append(load_manifest(manifest))
        except (ValueError, json.JSONDecodeError):
            continue
    return found


# --------------------------------------------------------------------------
# Routing manifest (compact, generated; routing reads ONLY this on hot path)
# --------------------------------------------------------------------------
# In-process cache of the last-seen routing manifest: the file is read once
# per process (or per change), never per request — this is the token-savings
# story behind the two-stage design.
_RM_MEMO = {"path": None, "mtime": None, "size": 0, "entries": None,
            "fingerprint": None}


def _ensure_routing_manifest(root_path: Path) -> tuple[list[dict], str, float]:
    """Return (entries, fingerprint, bytes_loaded_this_call)."""
    p = routing_manifest_path(root_path)
    try:
        mtime, size = p.stat().st_mtime_ns, p.stat().st_size
    except OSError:
        mtime, size = None, 0
    if (_RM_MEMO["path"] == str(p) and _RM_MEMO["mtime"] == mtime
            and _RM_MEMO["entries"] is not None):
        return _RM_MEMO["entries"], _RM_MEMO["fingerprint"], 0.0
    rm = load_routing_manifest(root_path)
    if rm is None:
        skills = discover_skills(root_path)
        entries = [skill_to_routing_entry(s) for s in skills]
        loaded = sum(Path(s.manifest_path).stat().st_size for s in skills)
        fingerprint = ""
    else:
        entries = rm.get("skills", [])
        loaded = float(size)
        fingerprint = routing_fingerprint(rm)
    _RM_MEMO.update({"path": str(p), "mtime": mtime, "size": size,
                     "entries": entries, "fingerprint": fingerprint})
    return entries, fingerprint, loaded


def skill_to_routing_entry(skill: Skill) -> dict:
    return {
        "name": skill.name,
        "summary": skill.description,
        "use_when": skill.use_when,
        "not_when": skill.not_when,
        "capabilities": skill.capabilities,
        "objects": skill.objects,
        "actions": skill.actions,
        "aliases": skill.aliases,
        "keywords": skill.keywords,
        "intents": {k: v for k, v in skill.intents.items()},
        "commands": [{"name": c["name"], "keywords": c["keywords"]}
                     for c in skill.commands],
        "conflicts_with": skill.conflicts_with,
        "fingerprint": manifest_fingerprint(Path(skill.manifest_path)),
        "needs_review": skill.bootstrap_generated,
    }


def build_routing_manifest(root: Path | None = None) -> dict:
    """Regenerate skill-registry/routing-manifest.json from manifests
    (the skill corpus remains the source of truth)."""
    root_path = root or DEFAULT_ROOT
    skills = discover_skills(root_path)
    manifest = {
        "schema_version": ROUTING_MANIFEST_SCHEMA_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skill_count": len(skills),
        "skills": [skill_to_routing_entry(s) for s in skills],
    }
    reg_dir = root_path / REGISTRY_DIR_NAME
    reg_dir.mkdir(parents=True, exist_ok=True)
    (reg_dir / ROUTING_MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def routing_manifest_path(root: Path | None = None) -> Path:
    return (root or DEFAULT_ROOT) / REGISTRY_DIR_NAME / ROUTING_MANIFEST_FILENAME


def load_routing_manifest(root: Path | None = None) -> dict | None:
    p = routing_manifest_path(root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def routing_fingerprint(rm: dict | None) -> str:
    """Fingerprint of the whole routing manifest (cache invalidation key)."""
    if not rm:
        return ""
    return hashlib.sha256(
        json.dumps(rm.get("skills", []), sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def build_registry(root: Path | None = None) -> dict:
    """Backward-compatible index (registry.json); still generated, but routing
    now consumes routing-manifest.json instead."""
    root_path = root or DEFAULT_ROOT
    skills = discover_skills(root_path)
    registry = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "skills_dir": SKILLS_DIR_NAME,
        "note": "Generated index. Source of truth: each skill's manifest.json.",
        "skill_count": len(skills),
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "commands": s.command_names,
                "manifest": str(Path(s.manifest_path).relative_to(root_path)),
            }
            for s in skills
        ],
    }
    reg_dir = root_path / REGISTRY_DIR_NAME
    reg_dir.mkdir(parents=True, exist_ok=True)
    (reg_dir / REGISTRY_FILENAME).write_text(
        json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return registry


def load_registry(root: Path | None = None) -> dict | None:
    reg_path = (root or DEFAULT_ROOT) / REGISTRY_DIR_NAME / REGISTRY_FILENAME
    if not reg_path.is_file():
        return None
    try:
        return json.loads(reg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------
# Cache (normalized request -> decision; invalidated on manifest change)
# --------------------------------------------------------------------------
_CACHE: dict[str, dict] = {}
_CACHE_FINGERPRINT = None
_LAST_CACHE_SAVE = [0.0]


def _cache_path(root: Path) -> Path:
    return root / REGISTRY_DIR_NAME / CACHE_FILENAME


def load_cache(root: Path, fingerprint: str) -> None:
    global _CACHE, _CACHE_FINGERPRINT
    if _CACHE_FINGERPRINT == fingerprint and fingerprint is not None:
        return  # already loaded for this manifest version
    _CACHE = {}
    _CACHE_FINGERPRINT = fingerprint
    if not CONFIG_ACTIVE["use_cache"]:
        return
    p = _cache_path(root)
    if not p.is_file():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("fingerprint") == fingerprint:
            _CACHE = data.get("entries", {})
    except (OSError, json.JSONDecodeError):
        _CACHE = {}


def save_cache(root: Path) -> None:
    """Persist the cache, throttled to ~1 write/second so the hot path is not
    paying for disk I/O on every request."""
    if not CONFIG_ACTIVE["use_cache"]:
        return
    now = time.monotonic()
    if now - _LAST_CACHE_SAVE[0] < 1.0:
        return
    try:
        payload = {"fingerprint": _CACHE_FINGERPRINT, "entries": _CACHE}
        _cache_path(root).write_text(json.dumps(payload, indent=2),
                                     encoding="utf-8")
        _LAST_CACHE_SAVE[0] = now
    except OSError:
        pass


def _cache_put(key: str, result: dict) -> None:
    if not CONFIG_ACTIVE["use_cache"]:
        return
    if len(_CACHE) >= CONFIG_ACTIVE["cache_size"]:
        _CACHE.clear()
    _CACHE[key] = result


# --------------------------------------------------------------------------
# Stage A — cheap candidate filtering (whole library, deterministic)
# --------------------------------------------------------------------------
def cheap_score(req: set[str], entry: dict) -> tuple[float, list[str]]:
    score = 0.0
    hits: list[str] = []
    name_t = phrase_tokens(entry["name"])
    if name_t and name_t <= req:
        score += CHEAP_WEIGHTS["name"]
        hits.append(f"name:{entry['name']}")
    for alias in entry.get("aliases", []):
        if phrase_full(req, alias):
            score += CHEAP_WEIGHTS["alias"]
            hits.append(f"alias:{alias}")
            break
    for trig in entry.get("use_when", []):
        if credit_ratio(req, trig) >= 0.5:
            score += CHEAP_WEIGHTS["use_when"]
            hits.append("use_when")
            break
    for phrases in entry.get("intents", {}).values():
        if any(credit_ratio(req, p) >= 0.5 for p in phrases):
            score += CHEAP_WEIGHTS["intent"]
            hits.append("intent")
            break
    for kw in entry.get("keywords", []):
        if phrase_full(req, kw):
            score += CHEAP_WEIGHTS["keyword"]
            hits.append("keyword")
            break
    for cap in entry.get("capabilities", []):
        if credit_ratio(req, cap) >= 0.5:
            score += CHEAP_WEIGHTS["capability"]
            hits.append("capability")
            break
    for obj in entry.get("objects", []):
        if credit_ratio(req, obj) >= 0.5:
            score += CHEAP_WEIGHTS["object"]
            hits.append("object")
            break
    for act in entry.get("actions", []):
        if credit_ratio(req, act) >= 0.5:
            score += CHEAP_WEIGHTS["action"]
            hits.append("action")
            break
    return round3(score), hits


# --------------------------------------------------------------------------
# Stage B — structured semantic ranking (candidate set only)
# --------------------------------------------------------------------------
def _best_ratio(req: set[str], phrases: list[str]) -> tuple[float, str | None]:
    best, best_p = 0.0, None
    for p in phrases:
        r = credit_ratio(req, p)
        if r > best:
            best, best_p = r, p
    return best, best_p


def rank_candidate(req: set[str], entry: dict) -> dict:
    """Structured score components for one candidate skill."""
    intent_r, intent_p = _best_ratio(req, [p for ps in entry.get("intents", {}).values() for p in ps])
    trig_r, trig_p = _best_ratio(req, entry.get("use_when", []))
    obj_r, obj_p = _best_ratio(req, entry.get("objects", []))
    act_r, act_p = _best_ratio(req, entry.get("actions", []))
    cap_r, cap_p = _best_ratio(req, entry.get("capabilities", []))

    def gated(r: float, floor: float = 0.5) -> float:
        return r if r >= floor else 0.0

    intent = gated(intent_r)
    obj = gated(obj_r)
    act = gated(act_r)
    cap = gated(cap_r)

    if trig_p is not None and trig_r >= 0.5:
        k = len(phrase_tokens(trig_p))
        trigger = min(0.9, trig_r * (0.40 + 0.12 * (k - 1)))
    else:
        trigger = 0.0

    name_alias = 0.0
    name_t = phrase_tokens(entry["name"])
    if name_t and name_t <= req:
        name_alias = 0.5
    else:
        for alias in entry.get("aliases", []):
            r = credit_ratio(req, alias)
            if r == 1.0:
                name_alias = 0.4
                break
            if r >= 0.5:
                name_alias = max(name_alias, 0.25)

    matched_phrases = [p for p, r in
                       ([(intent_p, intent_r), (trig_p, trig_r), (cap_p, cap_r)]
                        if intent_p or trig_p or cap_p else [])
                       if p and r >= 0.5]
    lens = [len(phrase_tokens(p)) for p in matched_phrases]
    specificity = min(1.0, 0.5 * (max(lens) / 5.0)) if lens else 0.0
    matched_tokens = set()
    for p in matched_phrases:
        matched_tokens |= phrase_tokens(p)
    if matched_tokens and matched_tokens <= GENERIC_WORDS:
        specificity = 0.0

    # Explicit call bonus: the request literally names this skill (name or a
    # full alias) AND the skill has at least one supporting anchor (object,
    # intent, action, capability, or domain). Without an anchor the name match
    # is dismissed — the word is likely used as an ordinary term
    # ('make my code impeccable' must NOT route to the prose skill).
    explicit = 0.0
    named = bool(name_t and name_t <= req) or any(
        credit_ratio(req, a) == 1.0 for a in entry.get("aliases", []))
    if named:
        # Anchor must be a FULL task-identity match (object / intent / domain).
        # Partial matches are not enough: 'write a design review of my backend
        # api' partially matches design-audit's intent 'review the frontend
        # design' (2/3 tokens) but the object is a backend api — no anchor, no
        # bonus. A generic action alone never anchors either.
        if max(intent, obj, _domain_match(req, entry)) >= 1.0:
            explicit = 1.0

    return {
        "intent": round3(intent), "object": round3(obj), "action": round3(act),
        "capability": round3(cap), "trigger": round3(trigger),
        "name_alias": round3(name_alias), "specificity": round3(specificity),
        "domain": round3(_domain_match(req, entry)), "explicit": explicit,
        "matched": {
            "intent": intent_p, "trigger": trig_p, "object": obj_p,
            "action": act_p, "capability": cap_p,
        },
    }


def _object_mismatch(req: set[str], entry: dict) -> tuple[float, list[str]]:
    """Penalize only when the request's concrete objects are ENTIRELY foreign
    to the skill. Partial coverage (one of several objects matches) is not a
    mismatch — e.g. 'review this pr ... and check the endpoint' still legitimately
    involves a pr for the code-review skill."""
    covered = set()
    for lst in (entry.get("objects", []), entry.get("capabilities", []),
                entry.get("keywords", []), entry.get("use_when", [])):
        for p in lst:
            covered |= phrase_tokens(p)
    covered |= phrase_tokens(entry["name"])
    # NOTE: not_when phrases deliberately do NOT count as coverage. If a skill
    # says not_when: 'backend architecture', the word 'backend' is a mismatch
    # signal for that skill, not coverage ('write a design review of my backend
    # api' must not route to the frontend design-audit skill).
    concrete = [t for t in req if t in CONCRETE_OBJECTS]
    if not concrete:
        return 0.0, []
    missing = [t for t in concrete if t not in covered]
    if len(missing) != len(concrete):
        return 0.0, []
    penalty = min(0.5, OBJECT_MISMATCH_PENALTY * len(missing))
    return penalty, missing


def _not_when_hit(req: set[str], entry: dict) -> str | None:
    for p in entry.get("not_when", []):
        if phrase_ratio(req, p) >= NOT_WHEN_DISQUALIFY_RATIO:
            return p
    return None


def _domain_match(req: set[str], entry: dict) -> float:
    covered: set[str] = set()
    for lst in (entry.get("objects", []), entry.get("capabilities", []),
                entry.get("keywords", []), entry.get("use_when", [])):
        for p in lst:
            covered |= phrase_tokens(p)
    covered |= phrase_tokens(entry["name"])
    return 1.0 if any(t in DOMAIN_WORDS and t in covered for t in req) else 0.0


# --------------------------------------------------------------------------
# Decision + multi-skill plans
# --------------------------------------------------------------------------
def _match_dimensions(req: set[str], entry: dict) -> set[str]:
    """Task-identity dimensions this skill matched: the WHAT and WHY
    (objects, intents, triggers), not the generic HOW (actions). Two skills
    may both 'write' yet handle different objects — shared actions alone must
    not make them the same task (blocks multi-skill plans and spurious
    conflicts)."""
    dims: set[str] = set()
    for p in entry.get("use_when", []):
        if credit_ratio(req, p) >= 0.5:
            dims.add(f"trigger:{p}")
    for pid, ps in entry.get("intents", {}).items():
        for p in ps:
            if credit_ratio(req, p) >= 0.5:
                dims.add(f"intent:{pid}:{p}")
    for p in entry.get("objects", []):
        if credit_ratio(req, p) >= 0.5:
            dims.add(f"object:{p}")
    return dims


def _order_hint(request: str) -> int:
    low = request.lower()
    if " then " in f" {low} " or low.startswith("then "):
        return 1
    if " first " in f" {low} ":
        return 1
    return 0


def try_multi_plan(req: set[str], ranked: list[dict], request: str,
                   cfg: dict) -> list[str] | None:
    """Build a minimal ordered multi-skill plan when >=2 skills match disjoint
    dimensions with sufficient confidence. Returns skill names or None."""
    floor = cfg["multi_floor"]
    top = ranked[0]
    if top["confidence"] < floor:
        return None
    plan = [top]
    used_dims = set(top["dims"])
    for cand in ranked[1:]:
        if len(plan) >= cfg["multi_cap"]:
            break
        if cand["confidence"] < floor:
            break
        if cand["dims"] & used_dims:
            continue  # overlapping — not complementary
        if not cand["dims"]:
            continue
        plan.append(cand)
        used_dims |= cand["dims"]
    if len(plan) < 2:
        return None
    if _order_hint(request):
        def pos(s: dict) -> int:
            # Position of the first matched OBJECT phrase in the request —
            # the trigger-phrase text often doesn't appear verbatim
            # ('rewrite the landing page copy' vs 'write landing page copy').
            best = 10 ** 9
            for p in s["entry"].get("objects", []):
                if credit_ratio(req, p) >= 0.5:
                    idx = request.lower().find(p[:40])
                    if idx != -1:
                        best = min(best, idx)
            return best
        plan.sort(key=pos)
    return [c["name"] for c in plan]


# --------------------------------------------------------------------------
# Routing (hot path)
# --------------------------------------------------------------------------
def _empty_result(request: str, reason: str) -> dict:
    return {
        "decision": "no_route", "status": "no_match",
        "intent": "unknown", "skill": None, "skills": [], "command": None,
        "confidence": 0.0, "evidence": reason,
        "validated": False, "alternatives": [], "available_commands": [],
        "cache_hit": False,
    }


def resolve_command(req: set[str], entry: dict) -> tuple[str | None, list[str]]:
    cmds = entry.get("commands", [])
    if not cmds:
        return None, []
    if len(cmds) == 1:
        return cmds[0]["name"], ["single-command"]
    best_name, best_score = None, 0.0
    for c in cmds:
        score = 0.0
        if phrase_tokens(c["name"]) & req:
            score += 0.55
        for kw in c.get("keywords", []):
            if phrase_full(req, kw):
                score += 0.30
                break
        if score > best_score:
            best_name, best_score = c["name"], score
    return best_name, (["single-command"] if best_score == 0 else [])


def route(request: str, root: Path | None = None, debug: bool = False,
          use_cache: bool = True) -> dict:
    """Route a request to the best skill / minimal skill set.

    Returns (minimal by default; --debug adds `debug`):
      decision: "route" | "ambiguous" | "no_route"
      skill / skills, confidence, command, evidence, alternative
    Legacy V1 fields (status/skill/command/confidence/validated/alternatives)
    are preserved for backward compatibility.
    """
    root_path = Path(root) if root else DEFAULT_ROOT
    cfg = CONFIG_ACTIVE
    req = tokens(request)
    _STATS["routes"] += 1

    result = _empty_result(request, "no matching skill")
    if not req:
        return result

    # --- compact routing manifest (memoized: one read per process) ---
    entries, fingerprint, loaded = _ensure_routing_manifest(root_path)
    _STATS["metadata_bytes_loaded"] += loaded

    # --- cache (hit path reads nothing). Debug requests bypass the cache. ---
    cache_key = normalize(request)
    load_cache(root_path, fingerprint)
    if use_cache and cfg["use_cache"] and not debug and cache_key in _CACHE:
        _STATS["cache_hits"] += 1
        hit = dict(_CACHE[cache_key])
        hit["cache_hit"] = True
        return hit
    _STATS["cache_misses"] += 1

    # --- stage A: cheap candidate filtering (whole library) ---
    scored_cheap = []
    for entry in entries:
        score, hits = cheap_score(req, entry)
        if score >= cfg["filter_floor"]:
            scored_cheap.append((score, entry, hits))
    scored_cheap.sort(key=lambda t: (-t[0], t[1]["name"]))
    candidates = [t for t in scored_cheap[: cfg["max_candidates"]]]
    if not candidates:
        _cache_put(cache_key, result)
        save_cache(root_path)
        return result

    # --- stage B: structured ranking on candidates only ---
    # Pass 1: raw confidence (not_when + object-mismatch penalties only).
    ranked = []
    total_w = sum(RANK_WEIGHTS.values())
    for score, entry, hits in candidates:
        comp = rank_candidate(req, entry)
        raw = sum(RANK_WEIGHTS[k] * comp[k] for k in RANK_WEIGHTS) / total_w
        raw += EXPLICIT_CALL_BONUS * comp["explicit"]
        penalties: list[str] = []
        neg = _not_when_hit(req, entry)
        if neg:
            # A negative trigger disqualifies only when the skill has no strong
            # positive anchor of its own. A mixed request (e.g. "review for
            # complexity AND check the endpoint for vulnerabilities") keeps the
            # skill as a candidate, just penalized, so multi-skill plans work.
            positive = (comp["intent"] * RANK_WEIGHTS["intent"]
                        + comp["trigger"] * RANK_WEIGHTS["trigger"]
                        + comp["object"] * RANK_WEIGHTS["object"]
                        + comp["action"] * RANK_WEIGHTS["action"])
            if positive < 0.15:
                raw *= 0.15
                penalties.append(f"not_when:'{neg}'")
            else:
                raw *= 0.6
                penalties.append(f"not_when(mixed):'{neg}'")
        mismatch, missing = _object_mismatch(req, entry)
        if mismatch:
            raw = max(0.0, raw - mismatch)
            penalties.append(f"object_mismatch:{','.join(missing)}")
        ranked.append({
            "name": entry["name"], "confidence": round3(min(1.0, raw)),
            "components": comp, "penalties": penalties, "cheap": score,
            "dims": _match_dimensions(req, entry), "entry": entry,
        })
    # Pass 2: conflict penalties — only when a conflicting skill is a REAL
    # competitor (comparable confidence) on the SAME task (overlapping dims).
    conf_by_name = {r["name"]: r["confidence"] for r in ranked}
    for r in ranked:
        conflicts = set(r["entry"].get("conflicts_with", []))
        if not conflicts:
            continue
        for other in ranked:
            if other["name"] not in conflicts:
                continue
            if not (other["dims"] & r["dims"]):
                continue  # disjoint tasks (multi-skill plans unaffected)
            if other["confidence"] < max(0.30, r["confidence"] - 0.10):
                continue  # not a real competitor
            r["confidence"] = round3(max(0.0, r["confidence"] - CONFLICT_PENALTY))
            r["penalties"].append(f"conflict:{other['name']}")
    ranked.sort(key=lambda r: (-r["confidence"], r["name"]))

    # --- decision ---
    decision: dict = {}
    plan = try_multi_plan(req, ranked, request, cfg)
    if plan:
        decision = {"decision": "route", "skills": plan,
                    "confidence": ranked[0]["confidence"]}
    else:
        best = ranked[0]
        second = ranked[1]["confidence"] if len(ranked) > 1 else 0.0
        if best["confidence"] >= cfg["route_floor"] and \
                best["confidence"] - second > cfg["ambiguity_gap"]:
            decision = {"decision": "route", "skills": [best["name"]],
                        "confidence": best["confidence"]}
        elif best["confidence"] >= cfg["no_route_floor"]:
            candidates_out = [r["name"] for r in ranked
                              if r["confidence"] >= cfg["no_route_floor"]][:4]
            decision = {"decision": "ambiguous", "candidates": candidates_out,
                        "confidence": best["confidence"]}
        else:
            _cache_put(cache_key, result)
            save_cache(root_path)
            return result

    # --- build result (minimal + legacy compat) ---
    if decision["decision"] == "route":
        primary = next(r for r in ranked if r["name"] == decision["skills"][0])
        cmd, cmd_hits = resolve_command(req, primary["entry"])
        evidence_parts = []
        for kind, phrase in primary["components"]["matched"].items():
            if phrase:
                evidence_parts.append(f"{kind} '{phrase}'")
        for p in primary["penalties"][:2]:
            evidence_parts.append(p)
        alternatives = [r["name"] for r in ranked[1:4]
                        if r["name"] not in decision["skills"]]
        status = "matched"
        intent = _detect_intent(req, primary["entry"])
        result = {
            "decision": "route",
            "status": "matched",
            "intent": intent or (f"{primary['name']}.{cmd}" if cmd else primary["name"]),
            "skill": decision["skills"][0],
            "skills": decision["skills"],
            "command": cmd,
            "confidence": round3(decision["confidence"]),
            "evidence": "; ".join(evidence_parts[:4]) or "no strong signal",
            "alternative": alternatives[0] if alternatives else None,
            "alternatives": alternatives,
            "validated": cmd is None or cmd in
            [c["name"] for c in primary["entry"].get("commands", [])],
            "available_commands":
                [c["name"] for c in primary["entry"].get("commands", [])],
            "cache_hit": False,
        }
    else:  # ambiguous
        result = {
            "decision": "ambiguous",
            "status": "ambiguous",
            "intent": "ambiguous",
            "skill": None,
            "skills": [],
            "candidates": decision["candidates"],
            "command": None,
            "confidence": round3(decision["confidence"]),
            "evidence": "top candidates too close to pick one safely",
            "alternative": decision["candidates"][1] if len(decision["candidates"]) > 1 else None,
            "alternatives": decision["candidates"][1:],
            "validated": False,
            "available_commands": [],
            "cache_hit": False,
        }
    if debug:
        result["debug"] = {
            "tokens": sorted(req),
            "fingerprint": fingerprint,
            "candidates": [
                {
                    "name": r["name"], "confidence": r["confidence"],
                    "cheap_score": r["cheap"], "penalties": r["penalties"],
                    "components": r["components"],
                } for r in ranked
            ],
        }

    _cache_put(cache_key, result)
    save_cache(root_path)
    return result


def _detect_intent(req: set[str], entry: dict) -> str | None:
    for pid, phrases in entry.get("intents", {}).items():
        if any(phrase_full(req, p) for p in phrases):
            return pid
    return None


def confidence_label(score: float) -> str:
    for floor, label in ((0.90, "very strong"), (0.75, "strong"),
                         (0.50, "possible"), (0.00, "weak")):
        if score >= floor:
            return label
    return "weak"


# --------------------------------------------------------------------------
# Bootstrap frontmatter parsing + candidate manifest generation (V1 compat)
# --------------------------------------------------------------------------
def parse_frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v and v != ">" and k not in out:
            out[k] = v
    return out


def guess_keywords(name: str, description: str) -> list[str]:
    kws = [name]
    seen = set(kws)
    for t in tokens(description):
        if t not in seen and len(kws) < 8:
            kws.append(t)
            seen.add(t)
    return kws


def guess_commands(skill_dir: Path, name: str, text: str) -> list[str]:
    cmds = []
    for tok in re.findall(r"`?/([a-z0-9][a-z0-9._-]*)`?", text):
        if tok not in cmds:
            cmds.append(tok)
    if not cmds:
        cmds.append(name)
    return cmds


def generate_candidate_manifest(skill_dir: Path) -> dict:
    name = skill_dir.name
    doc_path = skill_dir / SKILL_FILENAME
    text = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else ""
    front = parse_frontmatter(text)
    description = front.get("description") or (
        "Skill folder with no parseable description yet. See SKILL.md.")
    commands = [
        {"name": c, "syntax": c,
         "description": f"{name}: {description[:120]}",
         "keywords": [name]}
        for c in guess_commands(skill_dir, name, text)
    ]
    return {
        "name": name,
        "description": description,
        "keywords": guess_keywords(name, description),
        "aliases": [name],
        "capabilities": [description[:160]],
        "use_when": [],
        "not_when": [],
        "objects": [],
        "actions": [],
        "intents": {},
        "conflicts_with": [],
        "commands": commands,
        "_bootstrap": {"generated": True, "needs_review": True},
    }


# --------------------------------------------------------------------------
# Validation (includes corpus <-> routing-manifest drift detection)
# --------------------------------------------------------------------------
def validate_all(root: Path | None = None) -> dict:
    root_path = root or DEFAULT_ROOT
    skills_dir = root_path / SKILLS_DIR_NAME
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0

    if not skills_dir.is_dir():
        errors.append(f"skills directory missing: {skills_dir}")
        return {"ok": False, "errors": errors, "warnings": warnings,
                "skills_checked": 0, "commands_registered": []}

    manifest_fps: dict[str, str] = {}
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        manifest = entry / MANIFEST_FILENAME
        doc = entry / SKILL_FILENAME
        has_doc, has_manifest = doc.is_file(), manifest.is_file()
        if not has_doc and not has_manifest:
            continue
        if not has_doc:
            errors.append(f"{entry.name}: has manifest.json but no SKILL.md")
            continue
        if not has_manifest:
            errors.append(f"{entry.name}: skill has SKILL.md but no manifest.json "
                          "(not routable — create one or run bootstrap)")
            continue
        checked += 1
        try:
            skill = load_manifest(manifest)
        except (ValueError, json.JSONDecodeError) as e:
            errors.append(f"{entry.name}: invalid manifest — {e}")
            continue
        if skill.name != entry.name:
            errors.append(f"{entry.name}: manifest name '{skill.name}' does not "
                          f"match folder name")
        if skill.bootstrap_generated:
            warnings.append(f"{entry.name}: manifest is bootstrap-generated "
                            "(needs_review)")
        # V2 metadata quality checks
        if not skill.use_when:
            warnings.append(f"{entry.name}: no use_when triggers — add positive "
                            "routing boundaries")
        if skill.use_when and skill.not_when and not skill.objects:
            warnings.append(f"{entry.name}: has boundaries but no objects/actions "
                            "— structured signals incomplete")
        for a in skill.aliases:
            if a.lower() == skill.name and skill.aliases.count(a) > 1:
                warnings.append(f"{entry.name}: duplicate alias '{a}'")
        manifest_fps[skill.name] = manifest_fingerprint(manifest)

    # corpus <-> routing-manifest drift
    rm = load_routing_manifest(root_path)
    if rm is None:
        warnings.append(f"{REGISTRY_DIR_NAME}/{ROUTING_MANIFEST_FILENAME} missing "
                        "— run 'python3 skill.py sync'")
    else:
        for s in rm.get("skills", []):
            cur = manifest_fps.get(s["name"])
            if cur is None:
                errors.append(f"drift: routing manifest lists '{s['name']}' but "
                              "the skill folder/manifest is gone")
            elif cur != s.get("fingerprint"):
                errors.append(f"drift: routing manifest is stale for "
                              f"'{s['name']}' — run 'python3 skill.py sync'")
        for name in manifest_fps:
            if name not in {s["name"] for s in rm.get("skills", [])}:
                errors.append(f"drift: skill '{name}' missing from routing "
                              "manifest — run 'python3 skill.py sync'")

    registry = load_registry(root_path)
    if registry is None:
        warnings.append(f"{REGISTRY_DIR_NAME}/{REGISTRY_FILENAME} missing — run "
                        "'python3 skill.py discover' or 'sync'")
    elif registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        warnings.append("registry schema_version differs — regenerate with sync")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "skills_checked": checked,
        "commands_registered": sorted(
            c for s in discover_skills(root_path) for c in s.command_names),
    }


# --------------------------------------------------------------------------
# Bootstrap + sync
# --------------------------------------------------------------------------
def _contract_section() -> str:
    return (
        f"{CONTRACT_MARKER}\n"
        "# Skill Router V2\n"
        "\n"
        "This repository has a two-stage skill router. `skill.py` reads a\n"
        "compact generated routing manifest, filters candidates cheaply, ranks\n"
        "the candidate set semantically, and returns one of three decisions:\n"
        "`route` (recommended skill + command), `ambiguous` (ask the user), or\n"
        "`no_route` (handle directly). It may also propose a minimal ordered\n"
        "multi-skill plan. It never executes anything; you decide and execute.\n"
        "\n"
        "CLI: `python3 skill.py list | route \"<request>\" [--debug] | validate | sync | discover | benchmark`\n"
        "\n"
        "## Host-AI sanity check (mandatory, cheap)\n"
        "The router proposes; the host AI validates. On every `route` result,\n"
        "run a one-line check: does the selected skill clearly match the user's\n"
        "actual task (object + action)? If the evidence contradicts the\n"
        "request, ask the user instead of executing.\n"
        "\n"
        "## Maintenance contract (mandatory)\n"
        "Whenever a skill is installed, added, modified, or removed, you MUST\n"
        "synchronize the routing environment:\n"
        "\n"
        "* New skill: inspect it -> create/verify `skills/<name>/manifest.json`\n"
        "  (name matches the folder; register only commands that actually\n"
        "  exist; add `use_when`/`not_when`/`objects`/`actions` so the router\n"
        "  can distinguish it) -> `python3 skill.py sync` -> test with\n"
        "  `python3 skill.py route \"<sample request>\" [--debug]`.\n"
        "* Modified skill: update its manifest -> `sync` -> re-run any\n"
        "  affected gold-set cases (`python3 skill.py benchmark`).\n"
        "* Removed skill: delete the folder -> `sync` (registry and routing\n"
        "  manifest are regenerated; the stale cache is invalidated) ->\n"
        "  `validate`.\n"
        "\n"
        "## Operating rules\n"
        "* Execute only commands the router returned with `validated: true` —\n"
        "  a command missing from a discovered manifest is rejected, not run.\n"
        "* `route` -> recommend. `ambiguous` -> ask the user. `no_route` ->\n"
        "  handle directly or ask.\n"
        "* The router is deterministic. Treat `skill-registry/registry.json`\n"
        "  and `skill-registry/routing-manifest.json` as generated: edit\n"
        "  manifests, rebuild with `sync`. The cache invalidates itself on\n"
        "  manifest changes; `--no-cache` disables it.\n"
        "\n"
        "## Separation of responsibilities\n"
        "* `agent.md`: behavior, operating rules, this maintenance contract.\n"
        "* `skills/<name>/manifest.json`: skill identity, capabilities,\n"
        "  keywords, aliases, intents, commands, and routing boundaries\n"
        "  (source of truth).\n"
        "* `skill-registry/routing-manifest.json`: compact generated routing\n"
        "  metadata (never hand-edited).\n"
        "* `skill-registry/registry.json`: generated index (never hand-edited).\n"
        "* `skill.py`: filtering, ranking, decision, validation, cache.\n"
        "* You: interpret, sanity-check, decide, ask when ambiguous, execute.\n"
        f"\n{CONTRACT_MARKER}\n"
    )


def bootstrap(root: Path | None = None, force: bool = False) -> dict:
    root_path = (root or DEFAULT_ROOT).resolve()
    skills_dir = root_path / SKILLS_DIR_NAME
    skills_dir.mkdir(parents=True, exist_ok=True)

    generated, existing, regenerated = [], [], []
    for folder in skill_folders(root_path):
        manifest = folder / MANIFEST_FILENAME
        if manifest.is_file():
            existing.append(folder.name)
            if force:
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    marked = bool(data.get("_bootstrap", {}).get("generated"))
                except (json.JSONDecodeError, OSError):
                    marked = False
                if marked:
                    candidate = generate_candidate_manifest(folder)
                    manifest.write_text(
                        json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
                    regenerated.append(folder.name)
            continue
        candidate = generate_candidate_manifest(folder)
        manifest.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
        generated.append(folder.name)

    build_registry(root_path)
    build_routing_manifest(root_path)

    agent_md = root_path / AGENT_MD_FILENAME
    contract = _contract_section()
    agent_md_status = "already-had-contract"
    if agent_md.is_file():
        content = agent_md.read_text(encoding="utf-8")
        if CONTRACT_MARKER not in content:
            with open(agent_md, "a", encoding="utf-8") as fh:
                fh.write("\n\n" + contract)
            agent_md_status = "contract-appended"
    else:
        agent_md.write_text(
            "# Agent instructions\n\n(Add your project's operating rules here.)\n\n"
            + contract, encoding="utf-8")
        agent_md_status = "created"

    router_status = "already-present"
    router_path = root_path / ROUTER_FILENAME
    if not router_path.is_file():
        shutil.copy2(__file__, router_path)
        router_status = "installed"

    return {
        "root": str(root_path),
        "skills_generated": generated,
        "skills_with_manifests": existing,
        "candidates_regenerated": regenerated,
        "agent_md": agent_md_status,
        "skill_py": router_status,
        "registry_skills": len(existing) + len(generated),
        "note": "Generated candidate manifests carry '_bootstrap.needs_review' — "
                "add use_when/not_when/objects/actions when polishing.",
    }


def sync(root: Path | None = None) -> dict:
    root_path = root or DEFAULT_ROOT
    orphan_skills = [p.name for p in skill_folders(root_path)
                     if not (p / MANIFEST_FILENAME).is_file()]
    registry = build_registry(root_path)
    routing_manifest = build_routing_manifest(root_path)
    report = validate_all(root_path)
    return {
        "registry": registry,
        "routing_manifest": routing_manifest,
        "orphan_skills_without_manifests": orphan_skills,
        "validate": report,
        "idempotent": True,
    }


# --------------------------------------------------------------------------
# Benchmark (in-process gold-set evaluation)
# --------------------------------------------------------------------------
def run_benchmark_gold(gold_path: Path, root: Path | None = None) -> dict:
    import tempfile as _tf
    import time as _time
    cases_in = json.loads(gold_path.read_text(encoding="utf-8"))["cases"]
    corpus = DEFAULT_ROOT / "benchmarks" / "corpus" / "skills"
    scratch = Path(_tf.mkdtemp(prefix="skill-bench-"))
    if corpus.is_dir():
        for folder in corpus.iterdir():
            if folder.is_dir():
                shutil.copytree(folder, scratch / "skills" / folder.name)
    build_registry(scratch)
    build_routing_manifest(scratch)

    def case_ok(c: dict) -> bool:
        exp, got = c["expected"], c["decision"]
        if exp != got:
            return False
        exp_skills = set(c.get("expected_skills") or [])
        if exp == "route":
            return bool(exp_skills & set(c.get("skills") or []))
        if exp == "ambiguous":
            return bool(exp_skills & set(c.get("candidates") or []))
        return True

    results = []
    latencies: list[float] = []
    for case in cases_in:
        t0 = _time.perf_counter()
        payload = route(case["prompt"], root=scratch)
        ms = (_time.perf_counter() - t0) * 1000.0
        latencies.append(ms)
        entry = {
            "id": case["id"], "expected": case["expected"],
            "expected_skills": case.get("skills") or [],
            "decision": payload["decision"], "skill": payload["skill"],
            "skills": payload["skills"],
            "candidates": payload.get("candidates", []),
            "ms": round(ms, 3),
        }
        entry["ok"] = case_ok(entry)
        results.append(entry)
    n = len(results)
    ok = sum(1 for r in results if r["ok"])
    latencies.sort()
    return {
        "cases": results, "root": str(scratch),
        "ok": ok, "total": n,
        "accuracy": round(ok / n, 4) if n else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "latency_p95_ms": round(latencies[int(len(latencies) * 0.95)], 3) if latencies else 0.0,
    }


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------
def doctor(root: Path | None = None) -> dict:
    """Return actionable health information without changing the filesystem."""
    root_path = (root or DEFAULT_ROOT).resolve()
    report = validate_all(root_path)
    required = [root_path / ROUTER_FILENAME, root_path / SKILLS_DIR_NAME,
                root_path / REGISTRY_DIR_NAME / ROUTING_MANIFEST_FILENAME]
    missing = [str(p) for p in required if not p.exists()]
    report["root"] = str(root_path)
    report["version"] = VERSION
    report["missing"] = missing
    report["ok"] = report["ok"] and not missing
    if missing:
        report["errors"].append("installation is incomplete; run bootstrap or install.py")
    return report


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _usage() -> str:
    return (
        "skill.py — Portable Skill Router V2\n\n"
        "usage:\n"
        "  python3 skill.py bootstrap [--root DIR] [--force]    establish the routing environment\n"
        "  python3 skill.py sync [--root DIR]                   idempotent rebuild registry + routing manifest + validate\n"
        "  python3 skill.py discover [--root DIR]               rebuild registry + routing manifest\n"
        "  python3 skill.py list [--root DIR]                   print the skill index\n"
        "  python3 skill.py route \"<request>\" [--root DIR] [--debug] [--no-cache]   route a request\n"
        "  python3 skill.py validate [--root DIR]               validate manifests + registry + drift (exit 0/1)\n"
        "  python3 skill.py benchmark [--gold PATH]             run the gold-set benchmark\n"
        "  python3 skill.py stats                               print routing stats (cache, metadata bytes)\n"
        "  python3 skill.py doctor [--root DIR]                 diagnose installation and generated metadata\n"
        "  python3 skill.py --version                            print the router version\n"
    )


def _parse_args(argv: list[str]) -> dict:
    args = {"root": DEFAULT_ROOT, "force": False, "debug": False,
            "no_cache": False, "gold": None, "cmd": "", "request": ""}
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            args["root"] = Path(argv[i + 1]).resolve()
            i += 2
        elif a == "--force":
            args["force"] = True
            i += 1
        elif a == "--debug":
            args["debug"] = True
            i += 1
        elif a == "--no-cache":
            args["no_cache"] = True
            i += 1
        elif a == "--gold" and i + 1 < len(argv):
            args["gold"] = Path(argv[i + 1]).resolve()
            i += 2
        else:
            positional.append(a)
            i += 1
    args["cmd"] = positional[0] if positional else ""
    args["request"] = " ".join(positional[1:])
    return args


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(_usage())
        return 0
    if argv[0] in ("--version", "-V"):
        print(VERSION)
        return 0
    a = _parse_args(argv)
    cmd = a["cmd"]

    if cmd == "bootstrap":
        print(json.dumps(bootstrap(a["root"], force=a["force"]), indent=2))
    elif cmd == "sync":
        print(json.dumps(sync(a["root"]), indent=2))
    elif cmd == "discover":
        build_registry(a["root"])
        rm = build_routing_manifest(a["root"])
        print(json.dumps({"registry_skills": rm["skill_count"],
                          "routing_manifest": "rebuilt"}, indent=2))
    elif cmd == "list":
        rm = load_routing_manifest(a["root"])
        skills = rm["skills"] if rm else []
        for s in skills:
            cmds = ", ".join(c["name"] for c in s.get("commands", []))
            flag = " [needs_review]" if s.get("needs_review") else ""
            print(f"{s['name']:28s} commands: {cmds}{flag}")
        print(f"\n{len(skills)} skills")
    elif cmd == "route":
        if not a["request"]:
            print("error: 'route' needs a request string.", file=sys.stderr)
            print("  usage: python3 skill.py route \"<your request>\" --root <path>",
                  file=sys.stderr)
            return 2
        result = route(a["request"], root=a["root"], debug=a["debug"],
                       use_cache=not a["no_cache"])
        print(json.dumps(result, indent=2, default=str))
    elif cmd == "validate":
        report = validate_all(a["root"])
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    elif cmd == "benchmark":
        gold = a["gold"] or (DEFAULT_ROOT / "benchmarks" / "gold-set.json")
        out = run_benchmark_gold(gold, a["root"])
        n, ok = out["total"], out["ok"]
        print(f"gold-set cases: {n} | exact decision+skill matches: {ok}")
        for c in out["cases"]:
            mark = "OK " if c["ok"] else "XX "
            print(f"{mark}{c['id']:8s} exp={c['expected']:9s} "
                  f"got={c['decision']:9s} skills={c['skills']} "
                  f"({c['ms']} ms)")
        print(f"\naccuracy: {ok}/{n} = {out['accuracy']:.3f}")
        print(f"avg latency: {out['avg_latency_ms']:.3f} ms")
        print(f"p95 latency: {out['latency_p95_ms']:.3f} ms")
    elif cmd == "stats":
        print(json.dumps(get_stats(), indent=2))
    elif cmd == "doctor":
        report = doctor(a["root"])
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
