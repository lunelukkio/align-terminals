"""Print each terminal's drawn rectangle and the seams between neighbours.

Read-only. The arrange summary's `N of M` only proves each window matched its
own target; it cannot show whether neighbours actually touch. This measures the
drawn (client) rectangles, which is what a person sees, and subtracts adjacent
edges: a gap of 0 is the pass condition after an arrange.

Output is stable and hwnd-keyed so two runs can be diffed, which is how the
Rust implementation is compared against the Python oracle.

usage: py -3 tools/drawn_rects.py [label]
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

TERMINAL_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"
TERMINAL_PROCESS = "windowsterminal.exe"
GW_HWNDNEXT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.GetTopWindow.argtypes = [wintypes.HWND]
user32.GetTopWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
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


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"--- drawn rects {label}".rstrip())

    windows = []
    hwnd = user32.GetTopWindow(None)
    while hwnd:
        if (
            class_name(hwnd) == TERMINAL_CLASS
            and process_name(hwnd) == TERMINAL_PROCESS
            and user32.IsWindowVisible(hwnd)
        ):
            client = wintypes.RECT()
            origin = wintypes.POINT(0, 0)
            if user32.GetClientRect(
                hwnd, ctypes.byref(client)
            ) and user32.ClientToScreen(hwnd, ctypes.byref(origin)):
                windows.append(
                    (int(hwnd), origin.x, origin.y, client.right, client.bottom)
                )
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)

    windows.sort(key=lambda w: (w[2], w[1]))
    for hwnd, x, y, w, h in windows:
        print(f"  hwnd={hwnd} drawn=({x},{y},{w},{h})")

    lefts = sorted({x for _hwnd, x, _y, _w, _h in windows})
    for a, b in zip(lefts, lefts[1:]):
        width = next(w for _hwnd, x, _y, w, _h in windows if x == a)
        print(f"  seam x={a} (w={width}) -> x={b}: gap {b - (a + width)} px")
    tops = sorted({y for _hwnd, _x, y, _w, _h in windows})
    for a, b in zip(tops, tops[1:]):
        height = next(h for _hwnd, _x, y, _w, h in windows if y == a)
        print(f"  seam y={a} (h={height}) -> y={b}: gap {b - (a + height)} px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
