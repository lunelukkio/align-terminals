"""Record the Python layout() oracle for the Rust differential test.

Writes tests/fixtures/layout_cases.json covering n = 0..48 over several work
areas, including offset origins. Run again whenever align_terminals.pyw changes
layout(); tests/layout_differential.rs asserts the Rust port agrees on every
rect.

Usage: py -3 tools/gen_layout_fixture.py
"""

from __future__ import annotations

import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Origins are deliberately not all (0, 0): a taskbar docked top or left shifts
# the work area, and an origin bug would be invisible at the origin.
AREAS = [
    (0, 0, 1920, 1040),
    (0, 0, 1920, 1080),
    (0, 32, 1920, 1008),
    (100, 50, 2560, 1350),
    (0, 0, 1280, 720),
]


def load_module():
    """Import align_terminals.pyw, which the normal import machinery skips."""
    path = os.path.join(ROOT, "align_terminals.pyw")
    spec = importlib.util.spec_from_file_location("align_terminals", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_module()
    cases = []
    for area in AREAS:
        for count in range(0, 49):
            rects = module.layout(count, *area)
            cases.append(
                {
                    "count": count,
                    "area": list(area),
                    "rects": [list(rect) for rect in rects],
                }
            )
    out = os.path.join(ROOT, "tests", "fixtures", "layout_cases.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"cases": cases}, handle, separators=(",", ":"))
    print(f"wrote {len(cases)} cases -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
