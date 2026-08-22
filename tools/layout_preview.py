#!/usr/bin/env python3
"""Print the slot assignment of align_terminals.layout() without touching windows.

The arrangement itself only runs on Windows, but the layout is plain arithmetic, so
this renders the grid for a range of window counts and lets the mapping be checked
without opening that many terminals. It verifies arithmetic only: DPI behaviour shows
up in a real run on a mixed-DPI desktop and nowhere else.

Usage: python tools/layout_preview.py [max_count] [area_width] [area_height]
"""

from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CELL = 5


def load_module():
    """Import align_terminals.pyw, which the normal import machinery skips."""
    path = os.path.join(ROOT, "align_terminals.pyw")
    spec = importlib.util.spec_from_file_location("align_terminals", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def problems(rects, count, area_width, area_height):
    """Return the ways this layout fails to be a usable arrangement."""
    found = []
    if len(rects) != count:
        found.append(f"expected {count} rects, got {len(rects)}")
        return found
    for index, (left, top, width, height) in enumerate(rects, start=1):
        if left < 0 or left + width > area_width:
            found.append(f"window {index} sticks out horizontally")
        if top < 0 or top + height > area_height:
            found.append(f"window {index} sticks out vertically")
        if width <= 0 or height <= 0:
            found.append(f"window {index} has a non-positive size")
    if len(set(rects)) != len(rects):
        found.append("two windows share the same rect")
    tops = {left for left, top, _w, _h in rects if top == 0}
    bottoms = {left for left, top, _w, _h in rects if top != 0}
    if not bottoms <= tops:
        found.append("a bottom-row window has no column above it")
    return found


def render(module, count, area_width, area_height):
    rects = module.layout(count, 0, 0, area_width, area_height)
    if not rects:
        return f"n={count:2d}  (no window)"

    columns = sorted({left for left, _t, _w, _h in rects})
    slot = {}
    for index, (left, top, _w, _h) in enumerate(rects, start=1):
        slot[(columns.index(left), 0 if top == 0 else 1)] = index

    rows = 2 if any(top for _l, top, _w, _h in rects) else 1
    width = rects[0][2]
    offset = columns[1] - columns[0] if len(columns) > 1 else 0
    heights = "/".join(str(height) for height in sorted({r[3] for r in rects}))

    lines = [
        f"n={count:2d}  columns={len(columns)}  rows={rows}  "
        f"width={width}  offset={offset}  heights={heights}"
    ]
    for row in range(rows):
        cells = "".join(
            f"{slot.get((column, row), ''):>{CELL}}" for column in range(len(columns))
        )
        label = "top   " if row == 0 else "bottom"
        lines.append(f"      {label} |{cells} |")
    for problem in problems(rects, count, area_width, area_height):
        lines.append(f"      FAIL   {problem}")
    return "\n".join(lines)


def main() -> int:
    args = sys.argv[1:]
    max_count = int(args[0]) if len(args) > 0 else 12
    area_width = int(args[1]) if len(args) > 1 else 1920
    area_height = int(args[2]) if len(args) > 2 else 1040

    module = load_module()
    print(
        f"work area {area_width}x{area_height}, "
        f"OFFSET={module.OFFSET}, MIN_WIDTH={module.MIN_WIDTH}, "
        f"MAX_COLUMNS={module.MAX_COLUMNS}"
    )
    for count in range(1, max_count + 1):
        print(render(module, count, area_width, area_height))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
