from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load_installer():
    spec = importlib.util.spec_from_file_location("skill_install", REPO / "install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installer = load_installer()

    def test_project_plan_is_agent_specific_and_safe(self):
        root = Path(tempfile.mkdtemp(prefix="skill-install-"))
        pairs = self.installer.plan("project", "claude", root)
        self.assertTrue(all(str(target).startswith(str(root)) for _, target in pairs))
        self.assertIn(".claude/skills/skill-router", str(pairs[0][1]))
        self.assertIn(".skill-router/skill.py", str(pairs[-1][1]))

    def test_dry_run_does_not_write(self):
        root = Path(tempfile.mkdtemp(prefix="skill-install-"))
        result = subprocess.run(
            [sys.executable, str(REPO / "install.py"), "--scope", "project",
             "--project", str(root), "--dry-run"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((root / ".skill-router").exists())
        self.assertIn("Dry run", result.stdout)

    def test_install_and_refuse_unrelated_overwrite(self):
        root = Path(tempfile.mkdtemp(prefix="skill-install-"))
        first = subprocess.run(
            [sys.executable, str(REPO / "install.py"), "--scope", "project",
             "--project", str(root), "--yes"], capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        target = root / ".skill-router" / "skill.py"
        target.write_text("user file\n", encoding="utf-8")
        second = subprocess.run(
            [sys.executable, str(REPO / "install.py"), "--scope", "project",
             "--project", str(root), "--yes"], capture_output=True, text=True)
        self.assertEqual(second.returncode, 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "user file\n")

    def test_cli_version(self):
        result = subprocess.run([sys.executable, str(REPO / "skill.py"), "--version"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout.strip(), r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
