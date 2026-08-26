## Pull Request Checklist

- [ ] **What changed?** Describe the change in one or two sentences.
- [ ] **Why?** Explain the motivation (bug fix, routing improvement, infrastructure, docs, etc.).
- [ ] **Tests performed**
  - [ ] `python tests/run_tests.py` passes
  - [ ] `python skill.py validate --root .` exits 0
  - [ ] Routing regression cases added (if routing behavior changed)
- [ ] **Benchmark impact**
  - [ ] `python skill.py benchmark` shows no regression (or improvement)
  - [ ] Gold-set cases remain correct
- [ ] **Documentation impact**
  - [ ] `README.md` updated (if user-facing behavior changed)
  - [ ] `SKILL.md` updated (if skill contract changed)
  - [ ] `CONTRIBUTING.md` updated (if contributor workflow changed)
- [ ] **Breaking changes**
  - [ ] None
  - [ ] Listed below with migration instructions

**Additional notes**
