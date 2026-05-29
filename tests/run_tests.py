r"""Run every test_*.py module in this directory plus the smoke test.

Usage:
    .\.venv\Scripts\python.exe tests\run_tests.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TESTS_DIR = Path(__file__).resolve().parent


def _run_module(module_name: str, runner: str) -> int:
    module = importlib.import_module(module_name)
    func = getattr(module, runner)
    print(f"\n===== {module_name} =====")
    return func()


def main() -> int:
    failures = 0

    # smoke.py exposes main(); the test_*.py modules expose main_runner().
    failures += 1 if _run_module("tests.smoke", "main") else 0

    for path in sorted(TESTS_DIR.glob("test_*.py")):
        module_name = f"tests.{path.stem}"
        failures += 1 if _run_module(module_name, "main_runner") else 0

    print("\n=====================")
    if failures:
        print(f"{failures} test module(s) failed")
        return 1
    print("all test modules passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
