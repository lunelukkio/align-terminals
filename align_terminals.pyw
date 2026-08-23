#!/usr/bin/env python3
"""Tile Windows Terminal windows across the primary monitor work area.

Windows fill the work area in rows of at most five, always at full work-area height
per row. Two windows take half the width each, three take a third, and from four on
every window is a quarter of the width, so four tile exactly and five overlap evenly.
A sixth window starts a second row, an eleventh a third. When the count does not
divide evenly by the number of rows, the leftover windows become full-height columns
on the left.

A single window is only brought to the front; its size and position are left alone.

Running the script again puts the windows back where they were before the last run,
as long as nothing has moved since. A caller that knows which direction it wants can
ask for it outright instead of relying on that toggle. Only the Win32 API through
ctypes is used, so the script has no third-party dependencies.
"""

from __future__ import annotations

import json
import math
import os
import sys

# Windows a row holds before the layout adds another row.
MAX_PER_ROW = 5
# Columns that still tile without overlapping. Past this the width stops shrinking
# and the columns overlap instead, which is what keeps each window wide enough to read.
MAX_TILED_COLUMNS = 4

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
    visible. The order is the reading order of the grid. Any full-height column comes
    first, then the top row left to right, then the row below it, and so on. Sorting
    windows by (top, left) reproduces this order, which is what lets a second run
    hand every window back the slot it already occupies.

    A row holds at most MAX_PER_ROW windows, so the row count is count / MAX_PER_ROW
    rounded up. Within that, count // rows columns each hold one window per row and
    the count % rows windows left over become full-height columns on the left. Six
    windows are therefore three columns of two, seven are one full-height column plus
    three columns of two, and eight are four columns of two.

    Column width is the work area divided by the column count, but never by more than
    MAX_TILED_COLUMNS. Up to four columns tile exactly; a fifth keeps the quarter
    width and the columns overlap evenly instead, each still showing a readable band.
    Whatever the count, the columns spread from the left edge to the right edge.

    A lone window is not placed at all. Returning nothing here lets the caller raise
    it and leave its geometry untouched.
    """
    if count <= 1:
        return []

    rows = math.ceil(count / MAX_PER_ROW)
    # Windows that do not divide evenly into rows stand full height on the left.
    tall = count % rows
    columns = tall + count // rows

    width = area_width // min(columns, MAX_TILED_COLUMNS)
    offset = (area_width - width) // (columns - 1) if columns > 1 else 0
    row_height = area_height // rows

    rects = [
        (area_left + column * offset, area_top, width, area_height)
        for column in range(tall)
    ]
    for row in range(rows):
        # The last row takes the rounding remainder so the grid reaches the bottom.
        height = area_height - row * row_height if row == rows - 1 else row_height
        rects.extend(
            (area_left + column * offset, area_top + row * row_height, width, height)
            for column in range(tall, columns)
        )
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
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
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
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HANDLE
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
    MONITOR_DEFAULTTONULL = 0x0000
    SW_RESTORE = 9
    SW_MINIMIZE = 6
    HWND_TOP = wintypes.HWND(0)
    HWND_TOPMOST = wintypes.HWND(-1)
    HWND_NOTOPMOST = wintypes.HWND(-2)
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
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

    def content_rect(hwnd: int) -> "tuple[int, int, int, int] | None":
        """Where the terminal actually draws, in screen coordinates.

        This is the rectangle a person sees. It is smaller than window_rect, which
        also covers an invisible resize border, and it is what the layout should
        line up.
        """
        rect = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            return None
        return (origin.x, origin.y, rect.right, rect.bottom)

    def outset(hwnd: int, rect):
        """Grow a target rect by this window's invisible border.

        SetWindowPos positions the window rect, but the border it includes is not
        drawn, so windows placed edge to edge by those coordinates show a gap of two
        borders between them. Asking for a correspondingly larger rect puts the
        drawn edges where the layout wants them and closes the gap.

        The border is measured per window and per pass rather than assumed, because
        it is reported in the coordinate space of whichever monitor the window is on
        and this process is deliberately left DPI-unaware.

        An edge that would grow onto a neighbouring monitor is left alone. Since the
        process is DPI-unaware, coordinates outside the primary monitor are read in
        that monitor's scale, so such a request lands somewhere else entirely: asking
        for left -7 next to a 150% monitor puts the window at -5. Growing into empty
        space past the end of the desktop has no such problem and is allowed, which
        is what keeps the outermost edges flush.

        Returns the rect to ask SetWindowPos for together with the drawn rect that
        request will really produce. The two disagree wherever an edge could not
        grow, because the border keeps its size and eats into the slot instead.
        """
        frame = window_rect(hwnd)
        content = content_rect(hwnd)
        if frame is None or content is None:
            return rect, rect
        left, top, width, height = rect
        home = user32.MonitorFromPoint(
            wintypes.POINT(left + width // 2, top + height // 2), MONITOR_DEFAULTTONULL
        )

        def reachable(x: int, y: int) -> bool:
            found = user32.MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONULL)
            return not found or found == home

        border_left = content[0] - frame[0]
        border_top = content[1] - frame[1]
        border_right = (frame[0] + frame[2]) - (content[0] + content[2])
        border_bottom = (frame[1] + frame[3]) - (content[1] + content[3])

        pad_left, pad_top = border_left, border_top
        pad_right, pad_bottom = border_right, border_bottom
        if pad_left and not reachable(left - pad_left, top):
            pad_left = 0
        if pad_top and not reachable(left, top - pad_top):
            pad_top = 0
        if pad_right and not reachable(left + width + pad_right - 1, top):
            pad_right = 0
        if pad_bottom and not reachable(left, top + height + pad_bottom - 1):
            pad_bottom = 0

        request = (
            left - pad_left,
            top - pad_top,
            width + pad_left + pad_right,
            height + pad_top + pad_bottom,
        )
        drawn = (
            request[0] + border_left,
            request[1] + border_top,
            request[2] - border_left - border_right,
            request[3] - border_top - border_bottom,
        )
        return request, drawn

    def place(pairs, fill_gaps: bool) -> int:
        """Apply every geometry and count the calls Windows rejected.

        The final geometry is always asked for twice. A window that crosses a monitor
        DPI boundary receives WM_DPICHANGED once the move lands and rescales itself by
        the destination/source DPI ratio, overwriting the size that pass asked for.
        The repeat crosses no boundary, so its size holds. This is not a
        converge-by-retry loop: the repeat is what makes the size stick and a further
        pass changes nothing. Restoring crosses the boundary the other way and needs
        the repeat just as much.

        With fill_gaps the pairs carry the rect the drawn window should end up with,
        and a plain pass runs first. Its only job is to land every window on the
        target monitor, because until then the border is reported in the old
        monitor's scale, and for a moment after the rescale it is still off by a
        pixel. Only the two grown passes measure a border worth trusting, and the
        second of them is what corrects the first.

        Without fill_gaps the pairs carry window rects to reproduce exactly, which is
        what a restore wants.

        Geometry only. Z-order is left alone here so a restore cannot reshuffle it,
        and so raising stays in raise_to_front where it belongs.
        """
        rejected = 0
        flags = SWP_NOZORDER | SWP_NOACTIVATE
        passes = (False, True, True) if fill_gaps else (False, False)
        for grow in passes:
            for hwnd, rect in pairs:
                left, top, width, height = outset(hwnd, rect)[0] if grow else rect
                if not user32.SetWindowPos(
                    hwnd, HWND_TOP, left, top, width, height, flags
                ):
                    rejected += 1
        return rejected

    def raise_to_front(hwnds) -> int:
        """Lift each window to the front of the ordinary band, in the order given.

        Asking for HWND_TOP is not enough. A process that does not own the foreground
        window may not place another window above it, and Windows clamps the request
        to just underneath instead of failing, so SetWindowPos still reports success.
        Launched from a taskbar shortcut while a browser is in front, that leaves
        every terminal except the one that later takes focus behind the browser.

        Joining and leaving the topmost band is not clamped that way: HWND_TOPMOST
        puts the window above every ordinary window, and HWND_NOTOPMOST drops it back
        to the front of the ordinary band. Doing that left to right leaves the
        rightmost window in front, the same order the placement asks for.

        Geometry is untouched on purpose. A z-order-only call cannot trigger
        WM_DPICHANGED, so this pass stays clear of the two-pass placement above.
        """
        rejected = 0
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        for hwnd in hwnds:
            for insert_after in (HWND_TOPMOST, HWND_NOTOPMOST):
                if not user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, flags):
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
            rejected = place(pairs, fill_gaps=False)
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

    # A lone window has nothing to be tiled against, so the only thing worth doing is
    # what the arrangement is really for: getting the terminal out from behind
    # whatever is covering it. Its geometry is deliberately left untouched.
    if len(targets) == 1:
        rejected = raise_to_front(targets)
        user32.SetForegroundWindow(targets[0])
        summary = (
            "Only one Windows Terminal window is open; it was brought to the front "
            "and left at its current size and position."
        )
        if rejected:
            summary += f" {rejected} SetWindowPos call(s) were rejected."
        return _fail_gracefully(summary)

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

    def reading_order(hwnd):
        """Sort key matching the order layout() emits its rects in.

        Top row first and left to right within a row, so an already arranged set
        keeps every window in the slot it is in. Sorting by left first would
        interleave the rows of a split column and shuffle the windows on every run.
        """
        left, top, width, height = current[hwnd] or (0, 0, 0, 0)
        return (top, left, width, height)

    ordered = sorted(targets, key=reading_order)
    rects = layout(count, work_area.left, work_area.top, area_width, area_height)
    pairs = list(zip(ordered, rects))

    rejected = place(pairs, fill_gaps=True)
    rejected += raise_to_front([hwnd for hwnd, _rect in pairs])

    # Focus follows the frontmost window. Windows may refuse this while another
    # process holds the foreground lock, which is not worth failing the run over:
    # raise_to_front has already put every terminal in front either way.
    user32.SetForegroundWindow(ordered[-1])

    # SetWindowPos reports success even when the window ends up with different
    # geometry afterwards, so the summary counts measured rects rather than repeating
    # what was requested. Every window now has its own target, which makes this the
    # only check that still catches a DPI rescale. What is measured is the drawn
    # rectangle, because that is what the layout asked for; the window rect around it
    # is larger by a border whose size the layout never chose.
    # An edge that could not grow leaves the drawn rect short of its slot by the
    # border, so the target to check against is what outset() says is reachable.
    reachable_target = {hwnd: outset(hwnd, rect)[1] for hwnd, rect in pairs}
    drawn_after = {hwnd: content_rect(hwnd) for hwnd, _rect in pairs}
    placed = sum(
        1 for hwnd, _rect in pairs if drawn_after[hwnd] == reachable_target[hwnd]
    )

    # The snapshot records window rects instead, since a restore feeds them straight
    # back to SetWindowPos and has to reproduce them exactly.
    frames_after = {hwnd: window_rect(hwnd) for hwnd, _rect in pairs}
    arranged_entries = [
        {"hwnd": hwnd, "rect": list(frames_after[hwnd])}
        for hwnd, _rect in pairs
        if frames_after[hwnd] is not None
    ]
    remembered = len(arranged_entries) == count and len(previous_entries) == count
    if remembered:
        remembered = write_snapshot(arranged_entries, previous_entries)

    # Columns, rows and offset describe the layout that was asked for. The sizes are
    # read back off the screen, because those are what a DPI rescale would spoil and
    # what an edge that could not grow makes smaller than the slot.
    lefts = sorted({left for left, _top, _w, _h in rects})
    columns = len(lefts)
    rows = len({top for _left, top, _w, _h in rects})
    offset = lefts[1] - lefts[0] if columns > 1 else 0
    seen = [rect for rect in drawn_after.values() if rect is not None]
    widths = "/".join(f"{w}px" for w in sorted({r[2] for r in seen})) or "?"
    heights = "/".join(f"{h}px" for h in sorted({r[3] for r in seen})) or "?"
    summary = (
        f"Arranged {placed} of {count} Windows Terminal windows: "
        f"{columns} column(s), {rows} row(s), width {widths}, "
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
