"""Dump current Windows Terminal window rects to JSON for later restore."""
import ctypes, json, sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.OpenProcess.restype = wintypes.HANDLE

def cname(h):
    b = ctypes.create_unicode_buffer(256)
    n = user32.GetClassNameW(h, b, len(b))
    return b[:n] if n else ""

def pname(h):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    if not pid.value:
        return ""
    hp = kernel32.OpenProcess(0x1000, False, pid.value)
    if not hp:
        return ""
    try:
        size = wintypes.DWORD(1024)
        b = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(hp, 0, b, ctypes.byref(size)):
            return ""
        return b.value.rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(hp)

out = []
def collect(h, _l):
    if cname(h) != "CASCADIA_HOSTING_WINDOW_CLASS":
        return True
    if pname(h) != "windowsterminal.exe":
        return True
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    out.append({"hwnd": int(h), "x": r.left, "y": r.top,
                "w": r.right - r.left, "h": r.bottom - r.top,
                "minimized": bool(user32.IsIconic(h))})
    return True

user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(collect), 0)
path = sys.argv[1]
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(f"snapshot saved: {len(out)} windows -> {path}")
