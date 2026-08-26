#!/usr/bin/env python3
"""
Generate the benchmark skill corpus under benchmarks/corpus/skills/.

Each skill gets a SKILL.md (frontmatter + short body) and a manifest.json
in the V2 format (v1 fields + use_when / not_when / objects / actions /
conflicts_with). The corpus is deliberately *overlapping* so the gold set can
test near-neighbor, ambiguous, multi-skill, and adversarial routing.

Regenerate with:  python3 benchmarks/corpus/_generate.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_DIR = HERE / "skills"

# --------------------------------------------------------------------------
# Skill definitions
# --------------------------------------------------------------------------
# Each entry: name, summary, use_when, not_when, capabilities, objects,
# actions, aliases, keywords, intents {id: [phrases]}, conflicts_with,
# commands [{name, syntax, description, keywords}]
SKILLS: list[dict] = [
    {
        "name": "hallmark",
        "summary": "Judges whether text reads like a human wrote it: distinctive voice, naturalness, and the quality that separates human prose from machine output.",
        "use_when": ["judge if text sounds human written", "is this prose distinctive", "reads like a person wrote it", "check the voice of this writing", "human writing quality check", "sounds like a human wrote it"],
        "not_when": ["fix grammar mistakes", "proofread for typos", "remove ai cliches"],
        "capabilities": ["evaluate prose quality", "detect robotic writing", "assess writing voice", "judge human vs machine text"],
        "objects": ["text", "prose", "writing", "copy", "email", "essay", "chapter"],
        "actions": ["judge", "assess", "evaluate", "review", "check"],
        "aliases": ["hallmark", "human writing quality", "voice check", "human text check"],
        "keywords": ["hallmark", "human writing", "distinctive prose", "natural voice", "robotic writing"],
        "intents": {"human_check": ["sounds like a human wrote it", "reads like a person wrote it", "is this text human written"]},
        "conflicts_with": [],
        "commands": [{"name": "hallmark-check", "syntax": "hallmark-check <text>", "description": "Run a hallmark check on a piece of text.", "keywords": ["hallmark", "voice", "human"]}],
    },
    {
        "name": "impeccable",
        "summary": "Line-level editing: grammar, punctuation, spelling, and consistency. Proofreads and cleans up mechanical errors in text.",
        "use_when": ["fix grammar mistakes", "proofread this text", "correct spelling and punctuation", "clean up typos", "copy edit this document", "fix spelling and punctuation"],
        "not_when": ["restructure the whole piece", "rewrite in a different voice", "judge whether text is human"],
        "capabilities": ["grammar correction", "spelling and punctuation fixes", "style consistency"],
        "objects": ["text", "prose", "writing", "copy", "document", "essay", "paragraph"],
        "actions": ["proofread", "correct", "fix", "clean", "edit"],
        "aliases": ["impeccable", "proofreading", "grammar check", "copy editing"],
        "keywords": ["impeccable", "proofreading", "grammar", "punctuation", "typos", "copy editing"],
        "intents": {"proofread": ["fix grammar", "proofread this", "correct spelling", "clean up typos", "fix spelling and punctuation"]},
        "conflicts_with": ["hallmark"],
        "commands": [{"name": "proofread", "syntax": "proofread <text>", "description": "Proofread text for grammar, spelling, punctuation.", "keywords": ["grammar", "typos", "proofread"]}],
    },
    {
        "name": "antislop",
        "summary": "Strips AI-slop language from any text: cliche phrases like delve, seamless, tapestry, elevate, plus filler and buzzwords.",
        "use_when": ["remove ai cliches", "de-slop this text", "cut filler words", "remove buzzwords", "clean up cliches", "make this sound less like chatgpt", "clean up slop words"],
        "not_when": ["proofread for grammar", "evaluate writing quality", "rewrite for marketing"],
        "capabilities": ["remove ai slop phrases", "strip words like delve and seamless", "detect cliches", "tighten wordy text", "remove slop words like delve and seamless"],
        "objects": ["text", "prose", "writing", "copy", "email"],
        "actions": ["remove", "strip", "cut", "clean", "de-slop", "deslop"],
        "aliases": ["antislop", "de-slop", "deslop", "ai slop removal"],
        "keywords": ["antislop", "de-slop", "ai cliches", "buzzwords", "filler words", "slop"],
        "intents": {"deslop": ["remove ai cliches", "clean up cliches", "strip slop words", "de-slop this text", "clean up slop words"]},
        "conflicts_with": [],
        "commands": [{"name": "de-slop", "syntax": "de-slop <text>", "description": "Remove AI-slop phrases from text.", "keywords": ["slop", "cliches", "buzzwords"]}],
    },
    {
        "name": "antislop-heavy",
        "summary": "Strict de-slop for formal and academic documents: removes every slop phrase and flattens ornamental language in papers, theses, and reports.",
        "use_when": ["de-slop an academic paper", "remove cliches from a thesis", "strict de-slop for a report", "formal document cleanup", "remove slop from an academic paper"],
        "not_when": ["casual marketing copy", "quick email", "chat message"],
        "capabilities": ["strict slop removal", "formal writing cleanup", "academic tone"],
        "objects": ["paper", "thesis", "report", "academic text"],
        "actions": ["de-slop", "deslop", "tighten", "formalize", "strip"],
        "aliases": ["antislop heavy", "strict de-slop", "academic de-slop"],
        "keywords": ["strict", "academic", "thesis", "formal", "ornamental language"],
        "intents": {"strict_deslop": ["strict de-slop", "academic de-slop", "formal de-slop", "remove slop phrases"]},
        "conflicts_with": ["antislop"],
        "commands": [{"name": "de-slop-strict", "syntax": "de-slop-strict <document>", "description": "Strict de-slop for formal/academic documents.", "keywords": ["strict", "academic"]}],
    },
    {
        "name": "writing-beats",
        "summary": "Structural review of long-form writing: chapter-level beats, pacing, flow, and outline coherence for books and long articles.",
        "use_when": ["review chapter structure", "check the pacing of my book", "outline the beats", "long form structure review"],
        "not_when": ["line edits", "grammar fixes", "single paragraph"],
        "capabilities": ["pacing analysis", "structural review", "beat mapping"],
        "objects": ["book", "chapter", "article", "long form"],
        "actions": ["structure", "outline", "review", "map"],
        "aliases": ["writing beats", "beat review", "structure review"],
        "keywords": ["beats", "pacing", "structure", "outline", "chapters"],
        "intents": {"structure": ["review chapter structure", "check pacing", "outline beats"]},
        "conflicts_with": ["impeccable"],
        "commands": [{"name": "review-beats", "syntax": "review-beats <outline>", "description": "Review chapter-level beats and pacing.", "keywords": ["beats", "pacing", "structure"]}],
    },
    {
        "name": "design-audit",
        "summary": "Frontend design audit: visual design, UX, responsiveness, and design-system consistency. Reviews how an interface looks and feels.",
        "use_when": ["audit my frontend", "review the ui design", "visual design critique", "ux review of my app", "design system review", "ux review"],
        "not_when": ["write css from scratch", "set up the build", "backend architecture"],
        "capabilities": ["visual design review", "ux critique", "responsive design check", "design system consistency"],
        "objects": ["frontend", "ui", "design system", "landing page", "app", "interface", "website"],
        "actions": ["audit", "review", "critique", "evaluate"],
        "aliases": ["design-audit", "ui review", "frontend design audit", "design review"],
        "keywords": ["design audit", "ui review", "visual design", "ux", "responsive"],
        "intents": {"design_review": ["audit the ui", "review the frontend design", "visual design critique", "ux review"]},
        "conflicts_with": ["frontend-build"],
        "commands": [{"name": "audit-ui", "syntax": "audit-ui <url|screenshots>", "description": "Audit a frontend for design and UX issues.", "keywords": ["design", "ux", "visual"]}],
    },
    {
        "name": "accessibility-review",
        "summary": "Accessibility audit against WCAG: contrast, alt text, keyboard and screen-reader flow, and ARIA. More specific than a general design audit.",
        "use_when": ["check accessibility", "wcag compliance", "screen reader issues", "a11y audit", "contrast and alt text check"],
        "not_when": ["visual polish", "layout styling", "backend work"],
        "capabilities": ["wcag compliance", "screen reader testing", "contrast checks", "keyboard navigation"],
        "objects": ["web app", "dashboard", "site", "form", "interface"],
        "actions": ["audit", "check", "test", "verify"],
        "aliases": ["accessibility-review", "a11y review", "accessibility audit", "wcag audit"],
        "keywords": ["accessibility", "a11y", "wcag", "screen reader", "contrast", "alt text"],
        "intents": {"a11y": ["check accessibility", "wcag compliance", "screen reader test", "a11y audit"]},
        "conflicts_with": [],
        "commands": [{"name": "wcag-audit", "syntax": "wcag-audit <page>", "description": "Audit a page against WCAG.", "keywords": ["wcag", "a11y", "accessibility"]}],
    },
    {
        "name": "css-protips",
        "summary": "CSS tips and patterns: layout, flexbox and grid, responsive styling, and modern CSS for components and pages.",
        "use_when": ["css layout help", "style this component", "flexbox or grid tips", "write css for a page", "responsive styling"],
        "not_when": ["accessibility audit", "design critique", "build tooling"],
        "capabilities": ["css layout patterns", "responsive styling", "modern css techniques"],
        "objects": ["css", "layout", "component", "page", "stylesheet"],
        "actions": ["style", "write", "fix", "lay out"],
        "aliases": ["css-protips", "css tips", "styling help"],
        "keywords": ["css", "flexbox", "grid", "styling", "layout"],
        "intents": {"css_help": ["css layout help", "style this component", "css tips"]},
        "conflicts_with": ["design-audit"],
        "commands": [{"name": "css-tips", "syntax": "css-tips <question>", "description": "Give CSS layout and styling tips.", "keywords": ["css", "flexbox", "grid"]}],
    },
    {
        "name": "frontend-build",
        "summary": "Frontend build tooling: bundler configuration, vite and webpack setup, dependency and bundle optimization, and pipelines.",
        "use_when": ["set up the build", "vite config", "webpack bundle", "build tooling", "optimize the bundle"],
        "not_when": ["design review", "css styling", "ui critique"],
        "capabilities": ["build configuration", "bundle optimization", "tooling setup"],
        "objects": ["build", "bundler", "config", "pipeline", "tooling", "bundle"],
        "actions": ["configure", "set up", "optimize", "fix"],
        "aliases": ["frontend-build", "build setup", "tooling setup"],
        "keywords": ["vite", "webpack", "build", "bundler", "config"],
        "intents": {"build_setup": ["set up the build", "vite config", "webpack setup", "optimize the bundle"]},
        "conflicts_with": ["design-audit"],
        "commands": [{"name": "build-setup", "syntax": "build-setup <project>", "description": "Configure the frontend build.", "keywords": ["build", "vite", "webpack"]}],
    },
    {
        "name": "ponytail",
        "summary": "Reviews code diffs for unnecessary complexity: indirection, over-abstraction, and code that is harder than it needs to be.",
        "use_when": ["review this diff", "unnecessary complexity", "simplify this code", "code review for clarity", "over abstraction", "too much indirection"],
        "not_when": ["security vulnerabilities", "backend architecture", "frontend design"],
        "capabilities": ["complexity review", "code simplification", "diff review"],
        "objects": ["code", "diff", "pr", "pull request", "function"],
        "actions": ["review", "simplify", "refactor"],
        "aliases": ["ponytail", "complexity review"],
        "keywords": ["ponytail", "complexity", "simplification", "over abstraction", "indirection"],
        "intents": {"complexity": ["review this diff", "unnecessary complexity", "simplify this code", "too much indirection"]},
        "conflicts_with": [],
        "commands": [{"name": "ponytail-review", "syntax": "ponytail-review <diff>", "description": "Review a diff for unnecessary complexity.", "keywords": ["complexity", "diff", "simplify"]}],
    },
    {
        "name": "backend-review",
        "summary": "Backend architecture review: service boundaries, API design, data flow, and database modeling.",
        "use_when": ["review backend architecture", "service design review", "api architecture", "data flow review", "microservice boundaries"],
        "not_when": ["frontend", "css", "line level code review"],
        "capabilities": ["architecture review", "api design", "data modeling", "service boundaries"],
        "objects": ["backend", "api", "service", "database", "microservice"],
        "actions": ["review", "design", "evaluate", "map"],
        "aliases": ["backend-review", "architecture review"],
        "keywords": ["backend", "architecture", "microservice", "api design", "data flow"],
        "intents": {"architecture": ["review backend architecture", "api architecture", "service design"]},
        "conflicts_with": [],
        "commands": [{"name": "arch-review", "syntax": "arch-review <repo>", "description": "Review backend architecture.", "keywords": ["architecture", "backend"]}],
    },
    {
        "name": "security-review",
        "summary": "Security audit of code: vulnerabilities, injection, auth flaws, and OWASP-style checks on endpoints and applications.",
        "use_when": ["security audit", "find vulnerabilities", "check for injection", "auth issues", "endpoint security", "owasp check", "scan endpoint for vulnerabilities", "check endpoint for vulnerabilities"],
        "not_when": ["general code review", "style review", "complexity review"],
        "capabilities": ["vulnerability detection", "owasp checks", "auth review", "injection testing"],
        "objects": ["code", "api", "app", "auth", "endpoint"],
        "actions": ["audit", "scan", "test", "check"],
        "aliases": ["security-review", "security audit", "vuln check"],
        "keywords": ["security", "vulnerabilities", "injection", "owasp", "auth", "exploit"],
        "intents": {"security": ["security audit", "find vulnerabilities", "check for injection", "auth issues", "check endpoint for vulnerabilities"]},
        "conflicts_with": ["ponytail"],
        "commands": [{"name": "security-audit", "syntax": "security-audit <target>", "description": "Audit code for security issues.", "keywords": ["security", "vuln", "auth"]}],
    },
    {
        "name": "copywriting",
        "summary": "Marketing copywriting: landing pages, product descriptions, ads, and brand voice. Writes persuasive marketing text.",
        "use_when": ["write landing page copy", "marketing copy", "product description", "sales page", "draft an ad", "write marketing copy"],
        "not_when": ["technical documentation", "proofreading existing text"],
        "capabilities": ["marketing copy", "landing page text", "brand voice", "ad copy"],
        "objects": ["landing page", "marketing", "product", "ad", "brand"],
        "actions": ["write", "draft", "create", "rewrite"],
        "aliases": ["copywriting", "marketing writing"],
        "keywords": ["copywriting", "marketing", "landing page", "ad copy", "brand voice"],
        "intents": {"copy": ["write landing page copy", "marketing copy", "draft an ad", "draft marketing copy"]},
        "conflicts_with": [],
        "commands": [{"name": "write-copy", "syntax": "write-copy <brief>", "description": "Write marketing copy.", "keywords": ["copy", "marketing", "ad"]}],
    },
    {
        "name": "docs-writing",
        "summary": "Technical documentation: READMEs, user guides, and API docs. Explains how software works in clear written form.",
        "use_when": ["write a readme", "technical documentation", "api docs", "user guide", "document the codebase"],
        "not_when": ["marketing copy", "code review"],
        "capabilities": ["technical writing", "readme generation", "api documentation"],
        "objects": ["readme", "docs", "guide", "api", "codebase"],
        "actions": ["write", "document", "explain"],
        "aliases": ["docs-writing", "technical writing", "documentation"],
        "keywords": ["readme", "documentation", "api docs", "guide", "technical writing"],
        "intents": {"docs": ["write a readme", "api docs", "user guide", "technical documentation"]},
        "conflicts_with": ["copywriting"],
        "commands": [{"name": "write-docs", "syntax": "write-docs <topic>", "description": "Write technical documentation.", "keywords": ["docs", "readme", "guide"]}],
    },
    {
        "name": "data-viz",
        "summary": "Data visualization: charts, graphs, and dashboard plots. Writes code to visualize data.",
        "use_when": ["build a chart", "plot this data", "visualize the results", "dashboard chart", "graph this dataset"],
        "not_when": ["marketing", "design critique", "backend work"],
        "capabilities": ["chart code", "data visualization", "plotting"],
        "objects": ["chart", "graph", "dashboard", "data", "dataset"],
        "actions": ["plot", "visualize", "build", "chart"],
        "aliases": ["data-viz", "charts", "visualization"],
        "keywords": ["chart", "graph", "plot", "visualization", "dashboard"],
        "intents": {"viz": ["build a chart", "plot this data", "visualize the results"]},
        "conflicts_with": [],
        "commands": [{"name": "build-chart", "syntax": "build-chart <data>", "description": "Build a chart for the data.", "keywords": ["chart", "plot", "graph"]}],
    },
    {
        "name": "browser-automation",
        "summary": "Browser automation and end-to-end testing with Playwright: flows, selectors, and e2e scripts.",
        "use_when": ["end to end tests", "playwright script", "browser automation", "e2e test flow"],
        "not_when": ["unit tests", "accessibility audit", "css styling"],
        "capabilities": ["e2e testing", "playwright scripting", "browser flows"],
        "objects": ["browser", "e2e", "page", "test", "app"],
        "actions": ["automate", "test", "script", "run"],
        "aliases": ["browser-automation", "playwright", "e2e testing"],
        "keywords": ["playwright", "e2e", "browser automation", "test flow"],
        "intents": {"e2e": ["end to end tests", "playwright script", "browser automation"]},
        "conflicts_with": [],
        "commands": [{"name": "e2e-flow", "syntax": "e2e-flow <scenario>", "description": "Script a browser e2e flow.", "keywords": ["e2e", "playwright", "browser"]}],
    },
]


def write_skill(dir_path: Path, s: dict) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    doc = (
        "---\n"
        f"name: {s['name']}\n"
        f"description: {s['summary']}\n"
        "---\n"
        f"# {s['name']}\n\n"
        f"{s['summary']}\n\n"
        "## Commands\n"
    )
    for c in s["commands"]:
        doc += f"- `{c['syntax']}` — {c['description']}\n"
    (dir_path / "SKILL.md").write_text(doc, encoding="utf-8")

    manifest = {
        "name": s["name"],
        "description": s["summary"],
        "keywords": s["keywords"],
        "aliases": s["aliases"],
        "capabilities": s["capabilities"],
        "use_when": s["use_when"],
        "not_when": s["not_when"],
        "objects": s["objects"],
        "actions": s["actions"],
        "intents": s["intents"],
        "conflicts_with": s["conflicts_with"],
        "commands": s["commands"],
        "_bootstrap": {"generated": False, "needs_review": False},
    }
    (dir_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    for s in SKILLS:
        write_skill(SKILLS_DIR / s["name"], s)
    names = [s["name"] for s in SKILLS]
    print(f"wrote {len(names)} skills: {', '.join(names)}")
    total_bytes = sum(
        (SKILLS_DIR / n / "manifest.json").stat().st_size for n in names)
    print(f"total manifest bytes: {total_bytes}")


if __name__ == "__main__":
    main()
