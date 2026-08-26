#!/usr/bin/env python3
"""
Routing benchmark runner for Skill Router (version-agnostic: works against
the V1 and V2 routers because it only calls the public `route()` entry point
and reads whatever result shape the router emits).

Usage:
    python3 benchmarks/run_benchmark.py --repo /path/to/skill_by-_satya \\
        --gold benchmarks/gold-set.json [--repeat N] [--json out.json]

It builds a scratch repo from benchmarks/corpus/skills, runs `sync` to
generate registry artifacts, routes every gold-set case in-process, and
reports accuracy + efficiency metrics (latency, output size, metadata bytes
read, cache hits when the router exposes stats).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# Result parsing: map either result shape to a normalized decision
# --------------------------------------------------------------------------
def normalize_result(payload: dict) -> dict:
    """Return {decision, skill, skills, candidates, raw}."""
    if "decision" in payload:  # V2 shape
        decision = payload["decision"]
        skill = payload.get("skill")
        skills = payload.get("skills") or ([skill] if skill else [])
        candidates = payload.get("candidates") or []
        cand_names = [c if isinstance(c, str) else c.get("skill") for c in candidates]
        cand_names = [c for c in cand_names if c]
        return {"decision": decision, "skill": skill, "skills": skills,
                "candidates": cand_names, "raw": payload}
    # V1 shape
    status = payload.get("status")
    decision = {"matched": "route", "ambiguous": "ambiguous",
                "no_match": "no_route"}.get(status, "no_route")
    skill = payload.get("skill")
    candidates = [c.get("skill") for c in payload.get("candidates", [])]
    candidates = [c for c in candidates if c]
    return {"decision": decision, "skill": skill,
            "skills": [skill] if skill else [],
            "candidates": candidates, "raw": payload}


def returned_names(actual: dict, k: int = 3) -> list[str]:
    names: list[str] = []
    if actual["skill"]:
        names.append(actual["skill"])
    for c in actual["candidates"]:
        if c not in names:
            names.append(c)
    return names[:k]


# --------------------------------------------------------------------------
# Metric computation
# --------------------------------------------------------------------------
def compute_metrics(cases: list[dict], results: list[dict]) -> dict:
    n = len(cases)
    assert n == len(results)
    acc = t1 = topk = false_route = false_no_route = amb_prec = multi_ok = 0
    amb_tot = multi_tot = 0
    route_tot = 0
    for case, res in zip(cases, results):
        exp = case["expected"]
        exp_skills = set(case.get("skills") or [])
        act = res["actual"]
        names = returned_names(act, k=3)

        if act["decision"] == exp:
            acc += 1

        if exp == "route":
            route_tot += 1
            if act["decision"] == "route" and act["skill"] in (exp_skills | set(case.get("alternatives") or [])):
                t1 += 1
            if exp_skills & set(names):
                topk += 1
        elif exp in ("ambiguous", "no_route"):
            if act["decision"] == "route":
                false_route += 1

        if exp in ("route", "ambiguous") and act["decision"] == "no_route":
            false_no_route += 1

        if exp == "ambiguous":
            amb_tot += 1
            if act["decision"] == "ambiguous" and (exp_skills & set(names)):
                amb_prec += 1

        if exp == "route" and len(exp_skills) > 1:
            multi_tot += 1
            got = act["skills"]
            if case.get("ordered"):
                ok = got == case["skills"]
            else:
                ok = set(got) == exp_skills
            if ok:
                multi_ok += 1

    metrics = {
        "cases": n,
        "decision_accuracy": round(acc / n, 4) if n else 0.0,
        "top1_accuracy": round(t1 / route_tot, 4) if route_tot else 0.0,
        "top3_recall": round(topk / route_tot, 4) if route_tot else 0.0,
        "false_route_rate": round(false_route / max(1, n - route_tot), 4),
        "false_no_route_rate": round(false_no_route / max(1, n - (n - route_tot)), 4),
        "ambiguity_precision": round(amb_prec / amb_tot, 4) if amb_tot else 0.0,
        "multi_skill_correctness": round(multi_ok / multi_tot, 4) if multi_tot else 0.0,
    }
    lat = [r["ms"] for r in results]
    outb = [r["out_bytes"] for r in results]
    metb = [r["meta_bytes"] for r in results]
    metrics.update({
        "avg_latency_ms": round(sum(lat) / len(lat), 3),
        "avg_output_bytes": round(sum(outb) / len(outb), 1),
        "avg_metadata_bytes_per_route": round(sum(metb) / len(metb), 1),
        "cache_hit_rate": round(sum(r["cache_hit"] for r in results) / n, 4),
    })
    return metrics


# --------------------------------------------------------------------------
# Scratch repo + router loading
# --------------------------------------------------------------------------
def build_scratch(repo: Path, corpus: Path, stress: int = 1) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="skill-bench-"))
    skills_dir = tmp / "skills"
    (tmp / "agent.md").write_text("# Agent instructions\n", encoding="utf-8")
    for folder in sorted(corpus.iterdir()):
        if not folder.is_dir():
            continue
        target = skills_dir / folder.name
        shutil.copytree(folder, target)
        if stress > 1:
            data = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            for i in range(1, stress):
                dup = skills_dir / f"{folder.name}-{i}"
                shutil.copytree(folder, dup)
                d = json.loads((dup / "manifest.json").read_text(encoding="utf-8"))
                d["name"] = f"{folder.name}-{i}"
                (dup / "manifest.json").write_text(json.dumps(d, indent=2), encoding="utf-8")
    # generate registry / routing-manifest via the router's own sync
    subprocess.run([sys.executable, str(repo / "skill.py"), "sync", "--root", str(tmp)],
                   check=False, capture_output=True)
    return tmp


def load_router(repo: Path):
    import sys as _sys
    spec = importlib.util.spec_from_file_location("bench_skill", repo / "skill.py")
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["bench_skill"] = mod
    spec.loader.exec_module(mod)
    return mod


def _v1_meta_bytes(scratch: Path) -> float:
    total = 0
    for m in (scratch / "skills").rglob("manifest.json"):
        total += m.stat().st_size
    return float(total)


def run_benchmark(repo: Path, gold: Path, repeat: int, stress: int,
                  json_out: Path | None) -> dict:
    corpus = HERE / "corpus" / "skills"
    scratch = build_scratch(repo, corpus, stress)
    router = load_router(repo)
    cases = json.loads(gold.read_text(encoding="utf-8"))["cases"]

    if hasattr(router, "reset_stats"):
        router.reset_stats()

    def stats_snap():
        if hasattr(router, "get_stats"):
            st = router.get_stats()
            return st.get("cache_hits", 0), st.get("metadata_bytes_loaded", 0.0)
        return None

    results = []
    for case in cases:
        prompt = case["prompt"]
        best = None
        for _ in range(repeat):
            before = stats_snap()
            t0 = time.perf_counter()
            payload = router.route(prompt, root=scratch)
            ms = (time.perf_counter() - t0) * 1000.0
            after = stats_snap()
            if best is None or ms < best:
                best = ms
        actual = normalize_result(payload)
        if before is not None:
            hit = after[0] > before[0]
            meta = max(0.0, after[1] - before[1])
        else:
            hit = False
            meta = _v1_meta_bytes(scratch)
        out_bytes = len(json.dumps(payload, default=str))
        results.append({
            "id": case["id"],
            "expected": case["expected"],
            "expected_skills": case.get("skills") or [],
            "actual": actual,
            "ms": round(best, 3),
            "out_bytes": out_bytes,
            "meta_bytes": round(meta, 1),
            "cache_hit": hit,
        })

    metrics = compute_metrics(cases, results)
    out = {
        "router_version": getattr(router, "VERSION", "unknown"),
        "skills_in_corpus": len(list((scratch / "skills").iterdir())),
        "metrics": metrics,
        "per_case": results,
    }
    if json_out:
        json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"results written to {json_out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the routing gold-set benchmark.")
    ap.add_argument("--repo", default=str(HERE.parent),
                    help="path to the skill_by_satya repo containing skill.py")
    ap.add_argument("--gold", default=str(HERE / "gold-set.json"))
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--stress", type=int, default=1,
                    help="duplicate corpus this many times (scaling test)")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    out = run_benchmark(Path(args.repo), Path(args.gold), args.repeat,
                        args.stress, args.json)
    m = out["metrics"]
    print(f"router: {out['router_version']} | corpus skills: {out['skills_in_corpus']}")
    print(f"decision_accuracy      {m['decision_accuracy']}")
    print(f"top1_accuracy          {m['top1_accuracy']}")
    print(f"top3_recall            {m['top3_recall']}")
    print(f"false_route_rate       {m['false_route_rate']}")
    print(f"false_no_route_rate    {m['false_no_route_rate']}")
    print(f"ambiguity_precision    {m['ambiguity_precision']}")
    print(f"multi_skill_correct    {m['multi_skill_correctness']}")
    print(f"avg_latency_ms         {m['avg_latency_ms']}")
    print(f"avg_output_bytes       {m['avg_output_bytes']}")
    print(f"avg_meta_bytes/route   {m['avg_metadata_bytes_per_route']}")
    print(f"cache_hit_rate         {m['cache_hit_rate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
