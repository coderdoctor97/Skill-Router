#!/usr/bin/env python3
"""Test runner for the Skill Router regression suite.

Usage:  python3 tests/run_tests.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).resolve().parent), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
