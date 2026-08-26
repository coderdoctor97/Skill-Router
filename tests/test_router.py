#!/usr/bin/env python3
"""
Regression tests for the Skill Router.

Run:  python3 tests/run_tests.py
or:   python3 -m unittest discover -s tests -p "test_*.py"

Covers: routing decisions (route/ambiguous/no_route), multi-skill plans,
adversarial rejection, cache + invalidation, drift detection, bootstrap
idempotency, backward compatibility with V1 manifests, validation, and CLI
smoke tests — all against the benchmark corpus as fixtures.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "benchmarks" / "corpus" / "skills"
GOLD = REPO / "benchmarks" / "gold-set.json"


def load_router():
    spec = importlib.util.spec_from_file_location("test_skill", REPO / "skill.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["test_skill"] = mod
    spec.loader.exec_module(mod)
    return mod


def build_scratch(with_v1_skill: bool = False) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="skill-test-"))
    for folder in sorted(CORPUS.iterdir()):
        if folder.is_dir():
            shutil.copytree(folder, tmp / "skills" / folder.name)
    if with_v1_skill:
        v1 = tmp / "skills" / "legacy-skill"
        v1.mkdir(parents=True)
        (v1 / "SKILL.md").write_text(
            "---\nname: legacy-skill\ndescription: Legacy v1 skill for a retro review.\n---\n# Legacy\nRun `/legacy-review`.\n",
            encoding="utf-8")
        (v1 / "manifest.json").write_text(json.dumps({
            "name": "legacy-skill",
            "description": "Legacy v1 skill for a retro review.",
            "keywords": ["retro", "legacy"],
            "aliases": ["retro review"],
            "capabilities": ["retro review of code"],
            "intents": {"retro": ["retro review"]},
            "commands": [{"name": "legacy-review", "syntax": "legacy-review <diff>",
                          "description": "Retro review.", "keywords": ["retro"]}],
        }, indent=2), encoding="utf-8")
    return tmp


class RouterTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = load_router()
        cls.scratch = build_scratch()
        cls.router.sync(cls.scratch)

    def route(self, prompt: str):
        return self.router.route(prompt, root=self.scratch)

    # ---------------------------------------------------------- decisions
    def test_route_positive(self):
        cases = {
            "proofread this paragraph and fix the grammar mistakes": "impeccable",
            "de-slop my email, remove the ai cliches": "antislop",
            "audit my frontend for visual design issues": "design-audit",
            "check the accessibility of our dashboard against wcag": "accessibility-review",
            "review this pull request for unnecessary complexity": "ponytail",
            "write a readme for our new api client": "docs-writing",
            "set up vite and optimize the bundle": "frontend-build",
            "scan our login endpoint for vulnerabilities": "security-review",
            "strict de-slop for my thesis": "antislop-heavy",
            "build a chart from this dataset": "data-viz",
        }
        for prompt, skill in cases.items():
            with self.subTest(prompt=prompt):
                r = self.route(prompt)
                self.assertEqual(r["decision"], "route", r)
                self.assertEqual(r["skill"], skill, r)

    def test_near_neighbor_disambiguation(self):
        cases = {
            "the copy is grammatically fine but full of slop like delve and seamless, clean it up": "antislop",
            "fix the punctuation and spelling in this essay": "impeccable",
            "judge whether this chapter reads like a person wrote it": "hallmark",
            "check contrast, alt text, and screen reader flow on the form": "accessibility-review",
            "this diff is hard to follow, too much indirection": "ponytail",
            "review our microservice architecture and data flow": "backend-review",
        }
        for prompt, skill in cases.items():
            with self.subTest(prompt=prompt):
                r = self.route(prompt)
                self.assertEqual(r["decision"], "route", r)
                self.assertEqual(r["skill"], skill, r)

    def test_ambiguous(self):
        for prompt in ["review my writing", "help me with my frontend",
                       "review the code in this repo", "make my text better"]:
            with self.subTest(prompt=prompt):
                self.assertEqual(self.route(prompt)["decision"], "ambiguous")

    def test_no_route(self):
        for prompt in ["what is the weather like in berlin tomorrow?",
                       "solve this quadratic equation for x", "book a flight to tokyo"]:
            with self.subTest(prompt=prompt):
                self.assertEqual(self.route(prompt)["decision"], "no_route")

    def test_multi_skill_plans(self):
        r = self.route("rewrite the landing page copy, then de-slop it")
        self.assertEqual(r["decision"], "route")
        self.assertEqual(r["skills"], ["copywriting", "antislop"])  # ordered

        r = self.route("review this pr for complexity and check the new endpoint for vulnerabilities")
        self.assertEqual(r["decision"], "route")
        self.assertEqual(set(r["skills"]), {"ponytail", "security-review"})

        r = self.route("write a readme and draft the marketing blurb for the api")
        self.assertEqual(r["decision"], "route")
        self.assertEqual(set(r["skills"]), {"docs-writing", "copywriting"})

    def test_adversarial_rejection(self):
        # 'impeccable' is a prose skill; object is code -> never route to it
        r = self.route("make my code impeccable")
        self.assertNotEqual(r.get("skill"), "impeccable")
        # 'hallmark' is a prose skill; object is a react component -> never route to it
        r = self.route("run a hallmark check on my react component")
        self.assertNotEqual(r.get("skill"), "hallmark")
        # misleading phrase: object is the backend api -> backend-review wins
        r = self.route("write a design review of my backend api")
        self.assertEqual(r.get("skill"), "backend-review")

    def test_stemming_and_paraphrase(self):
        # V1 failed 'check accessibility' vs 'accessibility checks' (all-token
        # matching, no stemming). V2 must handle it.
        r = self.route("accessibility checks on our site")
        self.assertEqual(r["decision"], "route", r)
        self.assertEqual(r["skill"], "accessibility-review", r)

    # ------------------------------------------------------------ cache
    def test_cache_hits_and_invalidation(self):
        self.router.reset_stats()
        p = "check the accessibility of our dashboard against wcag"
        first = self.router.route(p, root=self.scratch)
        self.assertFalse(first["cache_hit"])
        second = self.router.route(p, root=self.scratch)
        self.assertTrue(second["cache_hit"])
        # registry change -> fingerprint changes -> cache invalidated
        skills_dir = self.scratch / "skills" / "accessibility-review"
        manifest = skills_dir / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["keywords"] = list(data["keywords"]) + ["updated-trigger-word"]
        manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.router.sync(self.scratch)
        third = self.router.route(p, root=self.scratch)
        self.assertFalse(third["cache_hit"], "stale cache must not survive registry change")

    # ------------------------------------------------------------ drift
    def test_drift_detection(self):
        manifest = self.scratch / "skills" / "antislop" / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["description"] = "changed without sync"
        manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        report = self.router.validate_all(self.scratch)
        self.assertFalse(report["ok"])
        self.assertTrue(any("drift" in e for e in report["errors"]), report["errors"])
        self.router.sync(self.scratch)
        report = self.router.validate_all(self.scratch)
        self.assertTrue(report["ok"], report["errors"])

    # ------------------------------------------------- backward compat
    def test_v1_manifest_still_routes(self):
        scratch = build_scratch(with_v1_skill=True)
        self.router.sync(scratch)
        r = self.router.route("do a retro review of the sprint", root=scratch)
        self.assertEqual(r["decision"], "route")
        self.assertEqual(r["skill"], "legacy-skill")
        self.assertEqual(r["command"], "legacy-review")

    # ------------------------------------------------------------ output
    def test_minimal_output_shape(self):
        r = self.route("proofread this paragraph and fix the grammar mistakes")
        # minimal default output: no score breakdown, no request echo
        self.assertNotIn("debug", r)
        self.assertNotIn("request", r)
        self.assertEqual(r["decision"], "route")
        self.assertTrue(r["validated"])
        self.assertIn("evidence", r)
        # debug mode adds the breakdown
        r2 = self.router.route("proofread this paragraph and fix the grammar mistakes",
                               root=self.scratch, debug=True)
        self.assertIn("debug", r2)
        self.assertIn("candidates", r2["debug"])

    def test_command_resolution_validated(self):
        r = self.route("review this pull request for unnecessary complexity")
        self.assertEqual(r["command"], "ponytail-review")
        self.assertTrue(r["validated"])
        self.assertIn("ponytail-review", r["available_commands"])


class BootstrapTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = load_router()

    def test_bootstrap_idempotent(self):
        tmp = Path(tempfile.mkdtemp(prefix="skill-boot-"))
        (tmp / "agent.md").write_text("# Agent\n", encoding="utf-8")
        # situation B: no skills yet
        r1 = self.router.bootstrap(tmp)
        self.assertEqual(r1["skills_generated"], [])
        # situation A: add a skill folder with only SKILL.md
        skill_dir = tmp / "skills" / "newbie"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: newbie\ndescription: Helps beginners with onboarding.\n---\n# Newbie\nRun `/onboard`.\n",
            encoding="utf-8")
        r2 = self.router.bootstrap(tmp)
        self.assertIn("newbie", r2["skills_generated"])
        self.assertTrue((skill_dir / "manifest.json").is_file())
        # a generated candidate is flagged for review and is NOT assumed
        # routable until the agent fills in routing boundaries
        cand = json.loads((skill_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(cand["_bootstrap"]["generated"])
        self.assertTrue(cand["_bootstrap"]["needs_review"])
        # second run: nothing changes
        r3 = self.router.bootstrap(tmp)
        self.assertEqual(r3["skills_generated"], [])
        self.assertEqual(r3["agent_md"], "already-had-contract")
        # simulate the agent's review: add routing boundaries, then sync
        cand["use_when"] = ["onboard the new developer", "onboard a new team member"]
        cand["objects"] = ["developer", "onboarding"]
        cand["actions"] = ["onboard", "help"]
        cand["intents"] = {"onboard": ["onboard the new developer", "onboard a new team member"]}
        cand["capabilities"] = ["team onboarding help"]
        cand["_bootstrap"]["needs_review"] = False
        (skill_dir / "manifest.json").write_text(json.dumps(cand, indent=2),
                                                 encoding="utf-8")
        self.router.sync(tmp)
        r4 = self.router.route("help me onboard the new developer", root=tmp)
        self.assertEqual(r4["decision"], "route")
        self.assertEqual(r4["skill"], "newbie")

    def test_validate_exit_codes_and_cli(self):
        tmp = build_scratch()
        # fresh: sync then validate -> exit 0
        subprocess.run([sys.executable, str(REPO / "skill.py"), "sync", "--root", str(tmp)],
                       check=True, capture_output=True)
        p = subprocess.run([sys.executable, str(REPO / "skill.py"), "validate", "--root", str(tmp)],
                           capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        # missing manifest -> error -> exit 1
        bad = tmp / "skills" / "broken"
        bad.mkdir()
        (bad / "SKILL.md").write_text("# Broken\n", encoding="utf-8")
        p = subprocess.run([sys.executable, str(REPO / "skill.py"), "validate", "--root", str(tmp)],
                           capture_output=True)
        self.assertEqual(p.returncode, 1)

    def test_cli_route_and_benchmark(self):
        tmp = build_scratch()
        subprocess.run([sys.executable, str(REPO / "skill.py"), "sync", "--root", str(tmp)],
                       check=True, capture_output=True)
        p = subprocess.run(
            [sys.executable, str(REPO / "skill.py"), "route",
             "check the accessibility of our dashboard against wcag", "--root", str(tmp)],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        payload = json.loads(p.stdout)
        self.assertEqual(payload["decision"], "route")
        self.assertEqual(payload["skill"], "accessibility-review")

        p = subprocess.run([sys.executable, str(REPO / "skill.py"), "benchmark"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("gold-set cases", p.stdout)

    def test_list_and_stats(self):
        tmp = build_scratch()
        subprocess.run([sys.executable, str(REPO / "skill.py"), "sync", "--root", str(tmp)],
                       check=True, capture_output=True)
        p = subprocess.run([sys.executable, str(REPO / "skill.py"), "list", "--root", str(tmp)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("16 skills", p.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
