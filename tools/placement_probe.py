"""Read taskbar reservation and terminal bounds without moving windows.

Exit 0: all visible terminals fit the reserved area; 1: an overflow was found;
2: taskbar or terminal windows are unavailable, so no desktop verdict is possible.
"""

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes

import drawn_rects as probe
from gen_layout_fixture import load_module


@contextmanager
def input_desktop():
    """Attach this reader thread to the input desktop; never switch the screen."""
    user32, kernel32 = probe.user32, probe.kernel32
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
    user32.GetThreadDesktop.restype = wintypes.HANDLE
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    user32.SetThreadDesktop.restype = wintypes.BOOL
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    previous = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
    desktop = user32.OpenInputDesktop(0, False, 0x0041)  # READOBJECTS | ENUMERATE
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    attached = False
    try:
        attached = bool(user32.SetThreadDesktop(desktop))
        if not attached:
            raise ctypes.WinError(ctypes.get_last_error())
        yield
    finally:
        if attached:
            user32.SetThreadDesktop(previous)
        user32.CloseDesktop(desktop)


def measure():
    oracle = load_module()
    area = oracle.primary_work_area()
    user32 = probe.user32
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    taskbar = user32.FindWindowW("Shell_TrayWnd", None)
    print(f"reserved_work_area={area}")
    print(f"taskbar_available={bool(taskbar)}")
    if taskbar:
        rect = wintypes.RECT()
        if user32.GetWindowRect(taskbar, ctypes.byref(rect)):
            print(f"taskbar_window=({rect.left},{rect.top},"
                  f"{rect.right - rect.left},{rect.bottom - rect.top})")
    windows = []
    hwnd = user32.GetTopWindow(None)
    while hwnd:
        if (probe.class_name(hwnd) == probe.TERMINAL_CLASS
                and probe.process_name(hwnd) == probe.TERMINAL_PROCESS
                and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd)):
            client, origin = wintypes.RECT(), wintypes.POINT()
            if (user32.GetClientRect(hwnd, ctypes.byref(client))
                    and user32.ClientToScreen(hwnd, ctypes.byref(origin))):
                windows.append((int(hwnd), (origin.x, origin.y, client.right, client.bottom)))
        hwnd = user32.GetWindow(hwnd, probe.GW_HWNDNEXT)
    print(f"visible_terminals={len(windows)}")
    if area is None or not taskbar or len(windows) < 2:
        print("UNVERIFIED: need a taskbar and at least two visible terminal windows.")
        return 2
    left, top, width, height = area
    overflow = False
    for hwnd, (x, y, w, h) in sorted(windows):
        inside = x >= left and y >= top and x + w <= left + width and y + h <= top + height
        print(f"hwnd={hwnd} drawn=({x},{y},{w},{h}) inside_reserved_area={inside}")
        overflow |= not inside
    return int(overflow)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-desktop", action="store_true",
                        help="read the interactive desktop from an isolated diagnostic desktop")
    args = parser.parse_args()
    if args.input_desktop:
        with input_desktop():
            return measure()
    return measure()


if __name__ == "__main__":
    raise SystemExit(main())
