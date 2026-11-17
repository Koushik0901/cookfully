#!/usr/bin/env python3
"""Say when a coverage floor can be raised.

Coverage floors only ever go up: each one sits just under what the suite measured when it was set,
so a change that quietly drops coverage fails CI. When the measured value climbs well above its
floor the floor is stale and the gap is slack a later regression could hide in. This prints a GitHub
notice for each floor that is at least ``--slack`` points below the measurement (default 2), with
the value to put in its place. It never fails the build and changes no file.

    python scripts/coverage-ratchet.py                 # reads backend/ and frontend/ coverage output
    python scripts/coverage-ratchet.py --slack 1.5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARGIN = 1.0  # a new floor sits this far under the measurement, as the existing ones do


def backend() -> tuple[str, float, float] | None:
    report = ROOT / "backend" / "coverage.xml"
    pyproject = ROOT / "backend" / "pyproject.toml"
    if not report.exists():
        return None
    # The gate (`fail_under`, with branch coverage on) counts lines and branches together,
    # not the XML's separate line-rate, so measure it the same way.
    root = ET.parse(report).getroot().attrib
    covered = int(root["lines-covered"]) + int(root["branches-covered"])
    valid = int(root["lines-valid"]) + int(root["branches-valid"])
    measured = covered / valid * 100
    floor = re.search(r"^fail_under\s*=\s*([\d.]+)", pyproject.read_text("utf-8"), re.MULTILINE)
    return ("backend total (backend/pyproject.toml fail_under)", measured, float(floor[1])) if floor else None


def frontend() -> list[tuple[str, float, float]]:
    summary = ROOT / "frontend" / "coverage" / "coverage-summary.json"
    config = ROOT / "frontend" / "vite.config.ts"
    if not summary.exists():
        return []
    total = json.loads(summary.read_text("utf-8"))["total"]
    text = config.read_text("utf-8")
    rows = []
    for metric in ("lines", "functions", "branches", "statements"):
        floor = re.search(rf"\b{metric}\s*:\s*([\d.]+)", text)
        if floor:
            rows.append(
                (f"frontend {metric} (frontend/vite.config.ts)", float(total[metric]["pct"]), float(floor[1]))
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--slack", type=float, default=2.0, help="points of headroom that trigger a notice")
    args = parser.parse_args()

    rows = [row for row in [backend(), *frontend()] if row is not None]
    if not rows:
        print("No coverage output found; run the tests with coverage first.", file=sys.stderr)
        return 0
    print(f"{'floor':<58}{'measured':>9}{'floor':>8}  suggestion")
    for name, measured, floor in rows:
        suggestion = int(measured - MARGIN)
        raise_it = measured - floor >= args.slack and suggestion > floor
        print(f"{name:<58}{measured:>8.1f}%{floor:>7.0f}%  {'raise to ' + str(suggestion) if raise_it else 'ok'}")
        if raise_it:
            print(
                f"::notice title=Coverage floor can be raised::{name} measured {measured:.1f}% "
                f"against a floor of {floor:g}%. Raise it to {suggestion}."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
