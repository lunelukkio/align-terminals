#!/usr/bin/env python3
"""Cascade Windows Terminal windows across the primary monitor work area.

Up to five windows are laid out left to right at full work-area height so each one
shows a readable left-edge band, and the rightmost window ends up in front. From the
sixth window on the layout gains a second row: the rightmost columns are split into a
top and a bottom half, and the split grows leftwards as more windows open.

Running the script again puts the windows back where they were before the last run,
as long as nothing has moved since. A caller that knows which direction it wants can
ask for it outright instead of relying on that toggle. Only the Win32 API through
ctypes is used, so the script has no third-party dependencies.
"""

from __future__ import annotations

import json
import os
import sys

# Band width reserved for each window behind the frontmost one.
OFFSET = 280
# Floor that keeps the layout usable if more windows are open than intended.
MIN_WIDTH = 640
# Columns the layout uses before it starts stacking a second row.
MAX_COLUMNS = 5

TERMINAL_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"
TERMINAL_PROCESS = "windowsterminal.exe"

# Bumped whenever the snapshot layout changes, so an old file is ignored rather than
# misread into a restore that moves windows somewhere unexpected.
SNAPSHOT_VERSION = 1

USAGE = """usage: align_terminals.pyw [--arrange | --restore]

  (no argument)  arrange, or put the windows back when none of them has moved since
                 the last run. This is what the taskbar shortcut uses.
  --arrange      always arrange, never restore.
  --restore      only restore. If a window has moved since the last run, report that
                 and change nothing.
"""


def snapshot_path() -> str:
    """Where the pre-arrangement positions are remembered between runs."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "align-terminals", "last_layout.json")


def layout(
    count: int,
    area_left: int,
    area_top: int,
    area_width: int,
    area_height: int,
) -> list[tuple[int, int, int, int]]:
    """Return one (left, top, width, height) per window, in placement order.

    Placement order is also z-order: each rect is raised in turn, so a window overlaps
    every window listed before it and the left edge band of the earlier ones stays
    visible. Index i is the i-th window counted from the left along the top row; once
    the top row is full the bottom row follows, again left to right.

    Up to MAX_COLUMNS windows share one full-height row. Beyond that the rightmost
    columns are split in half vertically and the extra windows fill the bottom half,
    so the split grows leftwards: the sixth window halves the last column, the seventh
    halves the one before it, and so on. Once every column is split the layout widens
    instead, keeping two rows.
    """
    if count <= 0:
        return []
    if count == 1:
        return [(area_left, area_top, area_width, area_height)]

    columns = count if count <= MAX_COLUMNS else max(MAX_COLUMNS, (count + 1) // 2)
    # Columns carrying a bottom-row window as well, counted from the right.
    split = count - columns

    width = min(max(MIN_WIDTH, area_width - (columns - 1) * OFFSET), area_width)
    offset = (area_width - width) // (columns - 1)
    top_height = area_height // 2
    first_split = columns - split

    rects = []
    for column in range(columns):
        left = area_left + column * offset
        height = area_height if column < first_split else top_height
        rects.append((left, area_top, width, height))
    for column in range(first_split, columns):
        left = area_left + column * offset
        rects.append((left, area_top + top_height, width, area_height - top_height))
    return rects


def _fail_gracefully(message: str) -> int:
    """Report why no window was moved and exit successfully."""
    print(message)
    return 0


def main() -> int:
    # A caller that means one direction says so; only the argument-free run guesses.
    args = sys.argv[1:]
    if args in (["--arrange"], ["--restore"]):
        mode = args[0][2:]
    elif not args:
        mode = "toggle"
    elif args in (["--help"], ["-h"]):
        print(USAGE, end="")
        return 0
    else:
        print(USAGE, end="", file=sys.stderr)
        return 2

    if sys.platform != "win32":
        return _fail_gracefully(
            "align-terminals only runs on Windows; no window was changed."
        )

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # HWND is a pointer, so it must be declared as such to stay correct on 64-bit.
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SystemParametersInfoW.argtypes = [
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    user32.SystemParametersInfoW.restype = wintypes.BOOL

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    SPI_GETWORKAREA = 0x0030
    SW_RESTORE = 9
    SW_MINIMIZE = 6
    HWND_TOP = wintypes.HWND(0)
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def class_name(hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        length = user32.GetClassNameW(hwnd, buffer, len(buffer))
        return buffer[:length] if length else ""

    def process_name(hwnd: int) -> str:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return ""
            return buffer.value.rsplit("\\", 1)[-1].lower()
        finally:
            kernel32.CloseHandle(handle)

    targets: list[int] = []

    enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    def collect(hwnd, _lparam):
        # A minimized window is not "visible" for layout purposes but must still be
        # collected, so visibility is only used to skip hidden helper windows.
        if class_name(hwnd) != TERMINAL_CLASS:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        if process_name(hwnd) != TERMINAL_PROCESS:
            return True
        targets.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc(collect), 0)

    if not targets:
        return _fail_gracefully(
            "No Windows Terminal window was found; nothing to arrange."
        )

    def window_rect(hwnd: int) -> "tuple[int, int, int, int] | None":
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    # The same geometry is applied twice on purpose. A window that crosses a monitor
    # DPI boundary receives WM_DPICHANGED once the move lands and rescales itself by
    # the destination/source DPI ratio, overwriting the size the first pass asked for.
    # After the first pass every window already sits on the primary monitor, so the
    # second pass crosses no boundary and its size holds. One repeat is enough; this
    # is not a converge-by-retry loop. Restoring crosses the boundary the other way
    # and needs the repeat just as much.
    def apply_twice(pairs, raise_windows: bool) -> int:
        """Apply every geometry twice and count the calls Windows rejected."""
        rejected = 0
        first = SWP_NOZORDER | SWP_NOACTIVATE
        # Raising left to right leaves the rightmost window in front and every
        # terminal above unrelated applications. A restore must not reshuffle z-order,
        # because the order the windows had before is not recorded.
        second = SWP_NOACTIVATE if raise_windows else first
        for flags in (first, second):
            for hwnd, (left, top, width, height) in pairs:
                if not user32.SetWindowPos(
                    hwnd, HWND_TOP, left, top, width, height, flags
                ):
                    rejected += 1
        return rejected

    def read_snapshot() -> "dict | None":
        try:
            with open(snapshot_path(), encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("version") != SNAPSHOT_VERSION:
            return None
        return data

    def write_snapshot(arranged: list, previous: list) -> bool:
        path = snapshot_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": SNAPSHOT_VERSION,
                        "arranged": arranged,
                        "previous": previous,
                    },
                    handle,
                    indent=2,
                )
        except OSError:
            return False
        return True

    def entries_by_hwnd(entries) -> "dict | None":
        """Index snapshot entries by window handle, or None if the file is malformed."""
        if not isinstance(entries, list):
            return None
        indexed = {}
        for entry in entries:
            try:
                indexed[int(entry["hwnd"])] = tuple(entry["rect"])
            except (KeyError, TypeError, ValueError):
                return None
            if len(indexed[int(entry["hwnd"])]) != 4:
                return None
        return indexed

    measured_now: dict[int, tuple[int, int, int, int]] = {}
    for hwnd in targets:
        rect = window_rect(hwnd)
        if rect is None:
            measured_now = {}
            break
        measured_now[hwnd] = rect

    # Restoring only happens when every window still sits exactly where the last run
    # left it. Anything moved by hand since then means the user is asking for a fresh
    # arrangement, not an undo, so an argument-free run arranges instead. An explicit
    # --restore reports the mismatch rather than quietly doing the opposite.
    snapshot = read_snapshot() if measured_now else None
    arranged_before = entries_by_hwnd(snapshot.get("arranged")) if snapshot else None
    already_arranged = arranged_before is not None and arranged_before == measured_now
    if mode != "arrange" and already_arranged:
        previous = entries_by_hwnd(snapshot.get("previous"))
        if previous is not None and set(previous) == set(measured_now):
            was_iconic = {
                int(entry["hwnd"])
                for entry in snapshot["previous"]
                if entry.get("iconic")
            }
            pairs = [(hwnd, previous[hwnd]) for hwnd in targets]
            rejected = apply_twice(pairs, raise_windows=False)
            restored = sum(
                1 for hwnd, rect in pairs if window_rect(hwnd) == rect
            )
            for hwnd in was_iconic:
                user32.ShowWindow(hwnd, SW_MINIMIZE)
            summary = (
                f"Restored {restored} of {len(pairs)} Windows Terminal windows to "
                f"their previous positions, measured after the move."
            )
            if was_iconic:
                summary += f" {len(was_iconic)} window(s) minimized again."
            if rejected:
                summary += f" {rejected} SetWindowPos call(s) were rejected."
            print(summary)
            return 0

    if mode == "restore":
        return _fail_gracefully(
            "The windows no longer match the last arrangement, so nothing was moved. "
            "Run without --restore to arrange them."
        )

    if len(targets) == 1:
        return _fail_gracefully(
            "Only one Windows Terminal window is open; no cascade is needed."
        )

    iconic = set()
    for hwnd in targets:
        if user32.IsIconic(hwnd):
            iconic.add(hwnd)
            user32.ShowWindow(hwnd, SW_RESTORE)

    work_area = wintypes.RECT()
    if not user32.SystemParametersInfoW(
        SPI_GETWORKAREA, 0, ctypes.byref(work_area), 0
    ):
        print("Could not read the primary monitor work area.", file=sys.stderr)
        return 1

    area_width = work_area.right - work_area.left
    area_height = work_area.bottom - work_area.top
    count = len(targets)

    # Measured after the restore above, so a window that was minimized is remembered
    # by the geometry it will have when it is shown again, not by the off-screen rect
    # Windows reports while it is iconic.
    current = {hwnd: window_rect(hwnd) for hwnd in targets}
    previous_entries = [
        {"hwnd": hwnd, "rect": list(rect), "iconic": hwnd in iconic}
        for hwnd, rect in current.items()
        if rect is not None
    ]
    # Arranging what is already arranged must not forget where the windows were before
    # the first run. Overwriting here would make a later restore undo nothing.
    if already_arranged:
        kept = entries_by_hwnd(snapshot.get("previous"))
        if kept is not None and set(kept) == set(targets):
            previous_entries = snapshot["previous"]

    ordered = sorted(targets, key=lambda hwnd: current[hwnd] or (0, 0, 0, 0))
    rects = layout(count, work_area.left, work_area.top, area_width, area_height)
    pairs = list(zip(ordered, rects))

    rejected = apply_twice(pairs, raise_windows=True)

    # Focus follows the frontmost window. Windows may refuse this while another
    # process holds the foreground lock, which is not worth failing the run over.
    user32.SetForegroundWindow(ordered[-1])

    # SetWindowPos reports success even when the window ends up with different
    # geometry afterwards, so the summary counts measured rects rather than repeating
    # what was requested. Every window now has its own target, which makes this the
    # only check that still catches a DPI rescale.
    measured_after = {hwnd: window_rect(hwnd) for hwnd, _rect in pairs}
    placed = sum(1 for hwnd, rect in pairs if measured_after[hwnd] == rect)

    arranged_entries = [
        {"hwnd": hwnd, "rect": list(measured_after[hwnd])}
        for hwnd, _rect in pairs
        if measured_after[hwnd] is not None
    ]
    remembered = len(arranged_entries) == count and len(previous_entries) == count
    if remembered:
        remembered = write_snapshot(arranged_entries, previous_entries)

    columns = sum(1 for _left, top, _w, _h in rects if top == work_area.top)
    rows = 1 if columns == count else 2
    heights = "/".join(f"{height}px" for height in sorted({r[3] for r in rects}))
    offset = rects[1][0] - rects[0][0] if columns > 1 else 0
    summary = (
        f"Arranged {placed} of {count} Windows Terminal windows: "
        f"{columns} column(s), {rows} row(s), width {rects[0][2]}px, "
        f"offset {offset}px, height {heights}, measured after placement."
    )
    if rejected:
        summary += f" {rejected} SetWindowPos call(s) were rejected."
    summary += (
        " Run again to put them back."
        if remembered
        else " Previous positions could not be saved, so running again will not"
        " restore them."
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
