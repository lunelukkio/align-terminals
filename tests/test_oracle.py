"""Exercise the real oracle entry point with deterministic Win32 responses.

The desktop double includes unequal invisible top borders, which reproduce
the raw-frame sorting bug without moving any real windows.
"""

import contextlib
import ctypes
import importlib.machinery
import importlib.util
import io
import itertools
import json
from pathlib import Path
import sys
import random
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("oracle", str(ROOT / "align_terminals.pyw"))
spec = importlib.util.spec_from_loader(loader.name, loader)
oracle = importlib.util.module_from_spec(spec)
loader.exec_module(oracle)


class Function:
    """Allow ctypes signatures to be assigned to a Python callable."""

    def __init__(self, call):
        self.call = call

    def __call__(self, *args):
        return self.call(*args)


class Library:
    def __init__(self, calls):
        self.calls = calls

    def __getattr__(self, name):
        def missing(*_args):
            raise AssertionError(f"unexpected Win32 call: {name}")

        call = Function(self.calls.get(name, missing))
        setattr(self, name, call)
        return call


def handle(value):
    return value.value if hasattr(value, "value") else value


def set_rect(pointer, rect):
    target = pointer._obj
    x, y, w, h = rect
    target.left, target.top, target.right, target.bottom = x, y, x + w, y + h
    return 1


class Desktop:
    def __init__(self):
        self.frames = {11: (0, 100, 500, 500), 22: (900, 100, 500, 500)}
        self.borders = {11: 8, 22: 9}
        self.order = [11, 22]
        self.minimized = set()
        self.monitor = (0, 0, 1920, 1080)
        self.work = self.monitor
        self.taskbar = (0, 1078, 1920, 48)
        self.edge = 3
        self.taskbar_monitor = 1
        self.taskbar_available = True
        self.moves = 0
        self.user32 = Library({
            "EnumWindows": self.enumerate,
            "GetClassNameW": self.class_name,
            "IsWindowVisible": lambda _h: 1,
            "IsIconic": lambda h: handle(h) in self.minimized,
            "GetWindowThreadProcessId": self.process_id,
            "GetWindowRect": self.window_rect,
            "GetClientRect": self.client_rect,
            "ClientToScreen": self.client_to_screen,
            "MonitorFromPoint": lambda *_: 1,
            "MonitorFromWindow": lambda *_: self.taskbar_monitor,
            "GetMonitorInfoW": self.monitor_info,
            "SystemParametersInfoW": lambda _a, _b, p, _c: set_rect(p, self.work),
            "FindWindowW": lambda *_: 99 if self.taskbar_available else 0,
            "SetWindowPos": self.place,
            "SetForegroundWindow": lambda _h: 1,
            "ShowWindow": self.show,
        })
        self.kernel32 = Library({
            "OpenProcess": lambda _a, _b, pid: pid,
            "QueryFullProcessImageNameW": self.process_name,
            "CloseHandle": lambda _h: 1,
        })
        self.shell32 = Library({"SHAppBarMessage": self.appbar})

    def enumerate(self, callback, param):
        for hwnd in self.order:
            callback(hwnd, param)
        return 1

    def class_name(self, _hwnd, buffer, _size):
        buffer.value = oracle.TERMINAL_CLASS
        return len(buffer.value)

    def process_id(self, hwnd, pointer):
        pointer._obj.value = handle(hwnd)
        return 1

    def process_name(self, _hwnd, _flags, buffer, size):
        buffer.value = "C:\\WindowsTerminal.exe"
        size._obj.value = len(buffer.value)
        return 1

    def window_rect(self, hwnd, pointer):
        hwnd = handle(hwnd)
        return set_rect(pointer, self.taskbar if hwnd == 99 else self.frames[hwnd])

    def drawn(self, hwnd):
        x, y, w, h = self.frames[hwnd]
        border = self.borders.get(hwnd, 8)
        return x, y + border, w, h - border

    def client_rect(self, hwnd, pointer):
        _x, _y, w, h = self.drawn(handle(hwnd))
        return set_rect(pointer, (0, 0, w, h))

    def client_to_screen(self, hwnd, pointer):
        x, y, _w, _h = self.drawn(handle(hwnd))
        pointer._obj.x, pointer._obj.y = x, y
        return 1

    def monitor_info(self, _monitor, pointer):
        info = pointer._obj
        x, y, w, h = self.monitor
        info.rcMonitor.left, info.rcMonitor.top = x, y
        info.rcMonitor.right, info.rcMonitor.bottom = x + w, y + h
        info.dwFlags = 1
        return 1

    def appbar(self, message, pointer):
        if message == 4:
            return 1
        if not self.taskbar_available:
            return 0
        data = pointer._obj
        data.uEdge = self.edge
        # Shell coordinates deliberately differ from the unaware process.
        data.rc.left, data.rc.top = 0, 2064
        data.rc.right, data.rc.bottom = 3840, 2160
        return 1

    def show(self, hwnd, action):
        if action == 6:
            self.minimized.add(handle(hwnd))
        else:
            self.minimized.discard(handle(hwnd))
        return 1

    def place(self, hwnd, _after, x, y, w, h, flags):
        hwnd = handle(hwnd)
        if not flags & 3:
            self.frames[hwnd] = x, y, w, h
            self.moves += 1
        return 1


class EntryPointTests(unittest.TestCase):
    def setUp(self):
        self.desktop = Desktop()
        (ROOT / "target").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "target")
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "snapshot.json"

    def run_app(self, *args):
        desktop = self.desktop
        libraries = {"user32": desktop.user32, "kernel32": desktop.kernel32,
                     "shell32": desktop.shell32}
        with patch.object(ctypes, "WinDLL", side_effect=lambda name, **_: libraries[name]), \
             patch.object(oracle, "snapshot_path", return_value=str(self.state)), \
             patch.object(sys, "argv", ["align_terminals.pyw", *args]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(oracle.main(), 0)
        return output.getvalue()

    def snapshot(self):
        return json.loads(self.state.read_text(encoding="utf-8"))

    def test_rearrange_keeps_window_slots_despite_unequal_frame_borders(self):
        self.run_app("--arrange")
        first = self.desktop.frames.copy()
        previous = self.snapshot()["previous"]
        self.desktop.order.reverse()
        self.run_app("--arrange")
        self.assertEqual(self.desktop.frames, first)
        self.assertEqual(self.snapshot()["previous"], previous)

    def test_auto_hide_taskbar_cannot_cover_the_last_line(self):
        self.run_app("--arrange")
        for hwnd in self.desktop.frames:
            _x, y, _w, h = self.desktop.drawn(hwnd)
            self.assertEqual(y + h, 1032)

    def test_taskbar_already_excluded_is_not_subtracted_twice(self):
        self.desktop.work = (0, 0, 1920, 1032)
        self.run_app("--arrange")
        for hwnd in self.desktop.frames:
            _x, y, _w, h = self.desktop.drawn(hwnd)
            self.assertEqual(y + h, 1032)

    def test_toggle_restores_and_explicit_restore_never_arranges(self):
        original = self.desktop.frames.copy()
        self.run_app("--arrange")
        self.run_app()
        self.assertEqual(self.desktop.frames, original)
        moves = self.desktop.moves
        self.run_app("--restore")
        self.assertEqual(self.desktop.moves, moves)

    def test_restore_then_arrange_returns_each_window_to_its_saved_seat(self):
        self.run_app("--arrange")
        arranged = self.desktop.frames.copy()
        self.run_app("--restore")
        self.desktop.order.reverse()
        self.run_app("--arrange")
        self.assertEqual(self.desktop.frames, arranged)

    def test_added_window_does_not_take_a_survivors_nearer_slot(self):
        self.run_app("--arrange")
        self.desktop.frames[33] = (0, 0, 500, 500)
        self.desktop.order = [33, 22, 11]
        self.run_app("--arrange")
        self.assertEqual([e["hwnd"] for e in self.snapshot()["arranged"]], [11, 33, 22])
        first = self.desktop.frames.copy()
        self.run_app("--arrange")
        self.assertEqual(self.desktop.frames, first)

    def test_deleted_window_then_restore_keeps_the_remaining_positions(self):
        self.test_added_window_does_not_take_a_survivors_nearer_slot()
        del self.desktop.frames[33]
        self.desktop.order = [22, 11]
        original = self.desktop.frames.copy()
        self.run_app("--arrange")
        self.assertEqual([e["hwnd"] for e in self.snapshot()["arranged"]], [11, 22])
        self.run_app("--restore")
        self.assertEqual(self.desktop.frames, original)

    def test_taskbar_on_another_monitor_or_missing_keeps_the_work_area(self):
        for available, monitor in [(False, 1), (True, 2)]:
            with self.subTest(available=available, monitor=monitor):
                self.desktop.taskbar_available = available
                self.desktop.taskbar_monitor = monitor
                self.run_app("--arrange")
                self.assertEqual(max(self.desktop.drawn(h)[1] + self.desktop.drawn(h)[3]
                                     for h in self.desktop.frames), 1080)

    def test_all_taskbar_edges_and_already_reserved_other_toolbars(self):
        cases = [
            (0, (-46, 0, 48, 1080), (48, 0, 1872, 1080)),
            (1, (0, -46, 1920, 48), (0, 48, 1920, 1032)),
            (2, (1918, 0, 48, 1080), (0, 0, 1872, 1080)),
            (3, (0, 1078, 1920, 48), (0, 0, 1920, 1032)),
        ]
        for edge, taskbar, area in cases:
            with self.subTest(edge=edge):
                self.desktop.edge, self.desktop.taskbar = edge, taskbar
                self.run_app("--arrange")
                self.assertEqual([self.desktop.drawn(e["hwnd"])
                                  for e in self.snapshot()["arranged"]],
                                 oracle.layout(2, *area))
        self.desktop.work = (0, 32, 1920, 988)
        self.run_app("--arrange")
        self.assertEqual([self.desktop.drawn(e["hwnd"])
                          for e in self.snapshot()["arranged"]],
                         oracle.layout(2, 0, 32, 1920, 988))

    def test_minimized_and_lone_window_contracts(self):
        self.desktop.minimized.add(11)
        self.run_app("--arrange")
        self.assertFalse(self.desktop.minimized)
        self.run_app("--restore")
        self.assertEqual(self.desktop.minimized, {11})
        self.desktop.frames.pop(22)
        self.desktop.order = [11]
        original = self.desktop.frames.copy()
        self.run_app("--arrange")
        self.assertEqual(self.desktop.frames, original)


class PolicyTests(unittest.TestCase):
    @staticmethod
    def movement(anchors, slots, assignment):
        return sum(sum((anchor[axis] + anchor[axis + 2] / 2
                        - slots[index][axis] - slots[index][axis + 2] / 2) ** 2
                       for axis in (0, 1))
                   for anchor, index in zip(anchors, assignment))

    def test_matching_minimizes_total_movement_against_exhaustive_search(self):
        rng = random.Random(1701)
        for n in range(1, 6):
            for m in range(n, 7):
                anchors = [(rng.randrange(-20, 20), rng.randrange(-20, 20), 7, 9)
                           for _ in range(n)]
                slots = [(rng.randrange(-20, 20), rng.randrange(-20, 20), 5, 11)
                         for _ in range(m)]
                chosen = oracle._nearest_slots(anchors, slots)
                self.assertEqual(len(set(chosen)), n)
                optimum = min(self.movement(anchors, slots, p)
                              for p in itertools.permutations(range(m), n))
                self.assertEqual(self.movement(anchors, slots, chosen), optimum)

    def test_removal_recalculates_nearest_seats_instead_of_compacting_order(self):
        previous = [(1, (0, 0, 100, 100)), (2, (100, 0, 100, 100)),
                    (3, (200, 0, 100, 100)), (4, (0, 100, 100, 100)),
                    (5, (100, 100, 100, 100)), (6, (200, 100, 100, 100))]
        current = previous[1:]
        slots = [(i * 50, 0, 100, 200) for i in range(5)]
        ordered = oracle.assign_slots(current, previous, slots)
        assignment = [ordered.index(hwnd) for hwnd, _ in current]
        anchors = [r for _, r in current]
        optimum = min(self.movement(anchors, slots, p)
                      for p in itertools.permutations(range(5)))
        self.assertEqual(self.movement(anchors, slots, assignment), optimum)

    def test_enumeration_order_cannot_change_equal_cost_assignment(self):
        rect = (50, 0, 100, 100)
        current = [(9, rect), (4, rect), (7, rect)]
        slots = oracle.layout(3, 0, 0, 1920, 1032)
        expected = oracle.assign_slots(current, [], slots)
        for permutation in itertools.permutations(current):
            self.assertEqual(oracle.assign_slots(permutation, [], slots), expected)

    def test_invalid_taskbar_measurements_keep_the_original_area(self):
        area = (0, 0, 1920, 1080)
        for edge, size in [(3, 0), (3, -48), (3, 1080), (0, 1921), (4, 48)]:
            self.assertEqual(oracle.reserve_taskbar(area, area, edge, size), area)


if __name__ == "__main__":
    unittest.main()
