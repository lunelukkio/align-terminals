"""Record taskbar and stable-seat policy cases from the Python oracle."""

import json
from pathlib import Path
import random

from gen_layout_fixture import load_module

ROOT = Path(__file__).resolve().parents[1]


def main():
    oracle = load_module()
    rng = random.Random(2718)
    assignments = []
    for old_count in range(2, 49):
        old_slots = oracle.layout(old_count, 0, 0, 1920, 1080)
        previous = [(i + 101, (x - 7, y - 7 - i % 2, w + 14, h + 14 + i % 2))
                    for i, (x, y, w, h) in enumerate(old_slots)]
        for count in (old_count - 1, old_count, old_count + 1):
            if count < 2 or count > 48:
                continue
            current = previous.copy()
            if count < old_count:
                current.pop(old_count // 2)
            elif count > old_count:
                current.append((10000 + old_count, (0, 0, 960, 540)))
            else:
                # A restore/manual move must not erase the saved seats.
                current = [(hwnd, (100, 100, 800, 500)) for hwnd, _ in current]
            rng.shuffle(current)
            slots = oracle.layout(count, 0, 0, 1920, 1032)
            assignments.append({"current": current, "previous": previous, "slots": slots,
                                "ordered": oracle.assign_slots(current, previous, slots)})
        # No history: includes exact ties, mixed-monitor positions and enumeration changes.
        current = [(i + 101, (rng.choice((-1200, 0, 400)), rng.choice((0, 300)), 800, 500))
                   for i in range(old_count)]
        rng.shuffle(current)
        slots = oracle.layout(old_count, 0, 0, 1920, 1032)
        assignments.append({"current": current, "previous": [], "slots": slots,
                            "ordered": oracle.assign_slots(current, [], slots)})

    taskbars = []
    for monitor, area in [
        ((0, 0, 1920, 1080), (0, 0, 1920, 1080)),
        ((0, 0, 1920, 1080), (48, 48, 1824, 984)),
        ((0, 0, 1920, 1080), (0, 32, 1920, 1000)),
        ((100, 50, 1280, 720), (100, 50, 1280, 720)),
    ]:
        for edge in range(5):
            for thickness in (-1, 0, 1, 48, 1080, 1920):
                taskbars.append({"area": area, "monitor": monitor, "edge": edge,
                                 "thickness": thickness,
                                 "expected": oracle.reserve_taskbar(area, monitor, edge, thickness)})
    output = ROOT / "tests" / "fixtures" / "placement_cases.json"
    output.write_text(json.dumps({"assignments": assignments, "taskbars": taskbars},
                                separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {len(assignments)} assignment and {len(taskbars)} taskbar cases")


if __name__ == "__main__":
    main()
