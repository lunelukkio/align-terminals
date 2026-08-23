"""Print the top-level window z-order, front to back, without changing anything.

Read-only. Used to check where the Windows Terminal windows sit relative to other
applications after an arrange, which is the one thing the arrange summary cannot
report: SetWindowPos returns success even when the foreground lock clamps a window
below the current foreground window.

The walk uses GetTopWindow + GW_HWNDNEXT rather than EnumWindows. EnumWindows happens
to visit windows in z-order today, but that is observed behavior and this is the one
measurement where the ordering is the data.

usage: py -3 tools/zorder_probe.py [label]
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

TERMINAL_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"

GW_HWNDNEXT = 2
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.DWORD
user32.GetTopWindow.argtypes = [wintypes.HWND]
user32.GetTopWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
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


def class_name(hwnd) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    length = user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer[:length] if length else ""


def window_title(hwnd) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    length = user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer[:length] if length else ""


def process_name(hwnd) -> str:
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


def rect_of(hwnd) -> str:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return "?"
    return (
        f"{rect.left},{rect.top} {rect.right - rect.left}x{rect.bottom - rect.top}"
    )


def ascii_only(text: str) -> str:
    """Console codepages here are not UTF-8; a CJK title would abort the probe."""
    return text.encode("ascii", "replace").decode("ascii")


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else ""
    foreground = user32.GetForegroundWindow()
    print(f"--- z-order {label}".rstrip())
    print(
        f"foreground: {process_name(foreground)} | "
        f"{ascii_only(window_title(foreground))[:60]}"
    )

    terminal_ranks: list[int] = []
    rank = 0
    hwnd = user32.GetTopWindow(None)
    while hwnd:
        # Untitled visible windows are shell scaffolding and only add noise; the
        # rank still counts them so the numbers match a raw walk.
        if user32.IsWindowVisible(hwnd) and window_title(hwnd):
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            marks = "".join(
                (
                    "T" if style & WS_EX_TOPMOST else "-",
                    "I" if user32.IsIconic(hwnd) else "-",
                    "F" if hwnd == foreground else "-",
                )
            )
            is_terminal = class_name(hwnd) == TERMINAL_CLASS
            if is_terminal:
                terminal_ranks.append(rank)
            print(
                f"  z{rank:<4} {marks} {process_name(hwnd):<22} "
                f"{rect_of(hwnd):<22} {ascii_only(window_title(hwnd))[:44]}"
            )
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
        rank += 1

    print(f"terminals at z: {terminal_ranks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
