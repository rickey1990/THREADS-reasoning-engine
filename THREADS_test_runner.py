#!/usr/bin/env python3
"""
THREADS public test runner
==========================

This file is intended as the simple entry point for a GitHub checkout.
It does not supply answers to THREADS.  It only launches the frozen tests
and reports whether the implementation's outputs match their independent
expectations/oracles.

Default (quick):
    python THREADS_test_runner.py

Full public benchmark set (heavier; Paper-10 includes a million-event test):
    python THREADS_test_runner.py --full

Individual groups:
    python THREADS_test_runner.py --regression
    python THREADS_test_runner.py --micro60
    python THREADS_test_runner.py --applied
    python THREADS_test_runner.py --paper10
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source"
BENCH = ROOT / "benchmarks"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def run(cmd: list[str], label: str, env: dict[str, str] | None = None) -> bool:
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    elapsed = time.perf_counter() - t0
    ok = proc.returncode == 0
    print(f"[{label}] {'PASS' if ok else 'FAIL'} in {elapsed:.3f}s")
    return ok


def python_env() -> dict[str, str]:
    env = os.environ.copy()
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SOURCE) + (os.pathsep + old if old else "")
    return env


def regression() -> bool:
    return run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(SOURCE / "tests"), "-v"],
        "Original regression suite",
        python_env(),
    )


def quick_micro() -> bool:
    # Five diagnostic categories plus several basic mathematical/temporal cases.
    cats = [1, 4, 21, 24, 31, 32, 41, 43, 46, 49, 55]
    out = RESULTS / "quick_micro.json"
    cmd = [
        sys.executable,
        str(BENCH / "micro60_suite.py"),
        str(SOURCE),
        "--out",
        str(out),
        "--only",
        *map(str, cats),
    ]
    return run(cmd, "Quick diagnostic microtests", python_env())


def micro60() -> bool:
    out = RESULTS / "micro60.json"
    return run(
        [sys.executable, str(BENCH / "micro60_suite.py"), str(SOURCE), "--out", str(out)],
        "60-category microbenchmark",
        python_env(),
    )


def applied() -> bool:
    a = run([sys.executable, str(BENCH / "applied10_benchmark.py")], "Applied-10 benchmark", python_env())
    b = run([sys.executable, str(BENCH / "applied10_robustness.py")], "Applied-10 randomized robustness", python_env())
    return a and b


def paper10() -> bool:
    out = RESULTS / "paper10.json"
    return run(
        [sys.executable, str(BENCH / "paper10_benchmark.py"), "--test", "all", "--out", str(out)],
        "Paper-10 scientific benchmark (heavy)",
        python_env(),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the public THREADS test suites.")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--full", action="store_true", help="run regression + micro60 + applied + Paper-10")
    group.add_argument("--regression", action="store_true", help="run only original regression tests")
    group.add_argument("--micro60", action="store_true", help="run the full 60-category microbenchmark")
    group.add_argument("--applied", action="store_true", help="run the two applied benchmark suites")
    group.add_argument("--paper10", action="store_true", help="run the 10 scientific headline experiments")
    args = ap.parse_args()

    print("THREADS public test runner")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Source: {SOURCE}")
    print("Note: expected outputs/oracles are used only for grading after THREADS computes its result.")

    if args.regression:
        checks = [("regression", regression())]
    elif args.micro60:
        checks = [("micro60", micro60())]
    elif args.applied:
        checks = [("applied", applied())]
    elif args.paper10:
        checks = [("paper10", paper10())]
    elif args.full:
        checks = [
            ("regression", regression()),
            ("micro60", micro60()),
            ("applied", applied()),
            ("paper10", paper10()),
        ]
    else:
        checks = [("regression", regression()), ("quick_micro", quick_micro())]

    summary = {name: ok for name, ok in checks}
    (RESULTS / "runner_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\nSUMMARY")
    for name, ok in checks:
        print(f"  {name:16s} {'PASS' if ok else 'FAIL'}")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
