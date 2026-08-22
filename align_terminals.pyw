#!/usr/bin/env python3
"""Cascade Windows Terminal windows across the primary monitor work area.

Windows are laid out left to right at full work-area height so each one shows a
readable left-edge band, and the rightmost window ends up in front. Only the Win32
API through ctypes is used, so the script has no third-party dependencies.
"""

from __future__ import annotations

import sys

# Band width reserved for each window behind the frontmost one.
OFFSET = 280
# Floor that keeps the layout usable if more windows are open than intended.
MIN_WIDTH = 640

TERMINAL_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"
TERMINAL_PROCESS = "windowsterminal.exe"


def _fail_gracefully(message: str) -> int:
    """Report why no window was moved and exit successfully."""
    print(message)
    return 0


def main() -> int:
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
        targets.append(hwnd)
        return True

    user32.EnumWindows(enum_proc(collect), 0)

    if not targets:
        return _fail_gracefully(
            "No Windows Terminal window was found; nothing to arrange."
        )
    if len(targets) == 1:
        return _fail_gracefully(
            "Only one Windows Terminal window is open; no cascade is needed."
        )

    for hwnd in targets:
        if user32.IsIconic(hwnd):
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

    width = max(MIN_WIDTH, area_width - (count - 1) * OFFSET)
    width = min(width, area_width)
    offset = (area_width - width) // (count - 1)

    def window_rect(hwnd: int) -> "wintypes.RECT | None":
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return rect

    def left_edge(hwnd: int) -> int:
        rect = window_rect(hwnd)
        return rect.left if rect else 0

    ordered = sorted(targets, key=left_edge)

    def place(hwnd: int, index: int, flags: int) -> bool:
        return bool(
            user32.SetWindowPos(
                hwnd,
                HWND_TOP,
                work_area.left + index * offset,
                work_area.top,
                width,
                area_height,
                flags,
            )
        )

    # The same geometry is applied twice on purpose. A window that crosses a monitor
    # DPI boundary receives WM_DPICHANGED once the move lands and rescales itself by
    # the destination/source DPI ratio, overwriting the size the first pass asked for.
    # After the first pass every window already sits on the primary monitor, so the
    # second pass crosses no boundary and its size holds. One repeat is enough; this
    # is not a converge-by-retry loop. The second pass also raises the windows left to
    # right, which leaves the rightmost one in front and every terminal above
    # unrelated applications.
    rejected = 0
    for index, hwnd in enumerate(ordered):
        if not place(hwnd, index, SWP_NOZORDER | SWP_NOACTIVATE):
            rejected += 1
    for index, hwnd in enumerate(ordered):
        if not place(hwnd, index, SWP_NOACTIVATE):
            rejected += 1

    # Focus follows the frontmost window. Windows may refuse this while another
    # process holds the foreground lock, which is not worth failing the run over.
    user32.SetForegroundWindow(ordered[-1])

    # SetWindowPos reports success even when the window ends up with different
    # geometry afterwards, so the summary counts measured rects rather than repeating
    # what was requested.
    def placed_as_requested(hwnd: int, index: int) -> bool:
        rect = window_rect(hwnd)
        if rect is None:
            return False
        return (
            rect.left == work_area.left + index * offset
            and rect.top == work_area.top
            and rect.right - rect.left == width
            and rect.bottom - rect.top == area_height
        )

    placed = sum(
        1 for index, hwnd in enumerate(ordered) if placed_as_requested(hwnd, index)
    )

    summary = (
        f"Arranged {placed} of {count} Windows Terminal windows: "
        f"width {width}px, offset {offset}px, height {area_height}px, "
        f"measured after placement."
    )
    if rejected:
        summary += f" {rejected} SetWindowPos call(s) were rejected."
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
