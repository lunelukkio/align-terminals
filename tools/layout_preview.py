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


def reading_order(rects):
    """The order a second run will sort the windows in: top row first, left to right."""
    return sorted(
        range(len(rects)), key=lambda i: (rects[i][1], rects[i][0], rects[i][2])
    )


def problems(rects, count, area_width, area_height):
    """Return the ways this layout fails to be a usable arrangement."""
    found = []
    if len(rects) != count:
        found.append(f"expected {count} rects, got {len(rects)}")
        return found
    if not rects:
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

    if max(left + width for left, _t, width, _h in rects) != area_width:
        found.append("the rightmost column does not reach the right edge")
    if max(top + height for _l, top, _w, height in rects) != area_height:
        found.append("the bottom row does not reach the bottom edge")

    tops = sorted({top for _l, top, _w, _h in rects})
    first_row = {left for left, top, _w, _h in rects if top == tops[0]}
    for top in tops[1:]:
        lefts = {left for left, other, _w, _h in rects if other == top}
        if not lefts <= first_row:
            found.append(f"a window at top={top} has no column above it")

    # A second run reassigns windows by reading order. If that disagrees with the
    # order layout() emits, an already arranged set swaps windows between slots.
    if reading_order(rects) != list(range(len(rects))):
        found.append("re-arranging would shuffle windows between slots")
    return found


def render(module, count, area_width, area_height):
    rects = module.layout(count, 0, 0, area_width, area_height)
    if not rects:
        reason = "raised only, not moved" if count == 1 else "no window"
        return f"n={count:2d}  ({reason})"

    columns = sorted({left for left, _t, _w, _h in rects})
    rows = sorted({top for _l, top, _w, _h in rects})
    full_height = {
        left for left, _t, _w, height in rects if height == area_height
    }

    slot = {}
    for index, (left, top, _w, height) in enumerate(rects, start=1):
        first = rows.index(top)
        last = len(rows) if height == area_height else first + 1
        for row in range(first, last):
            slot[(columns.index(left), row)] = index

    width = rects[0][2]
    offset = columns[1] - columns[0] if len(columns) > 1 else 0
    overlap = max(0, width - offset) if len(columns) > 1 else 0
    heights = "/".join(str(height) for height in sorted({r[3] for r in rects}))

    lines = [
        f"n={count:2d}  columns={len(columns)}  rows={len(rows)}  "
        f"width={width}  offset={offset}  overlap={overlap}  "
        f"tall={len(full_height) if len(rows) > 1 else 0}  heights={heights}"
    ]
    for row in range(len(rows)):
        cells = "".join(
            f"{slot.get((column, row), ''):>{CELL}}" for column in range(len(columns))
        )
        lines.append(f"      row {row} |{cells} |")
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
        f"MAX_PER_ROW={module.MAX_PER_ROW}, "
        f"MAX_TILED_COLUMNS={module.MAX_TILED_COLUMNS}"
    )
    for count in range(1, max_count + 1):
        print(render(module, count, area_width, area_height))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
