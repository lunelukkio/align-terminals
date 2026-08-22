"""Restore Windows Terminal window rects from a snapshot JSON."""
import ctypes, json, sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.IsWindow.argtypes = [wintypes.HWND]

with open(sys.argv[1], encoding="utf-8") as f:
    snap = json.load(f)

SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
for w in snap:
    h = wintypes.HWND(w["hwnd"])
    if not user32.IsWindow(h):
        print(f"  hwnd={w['hwnd']} no longer exists; skipped")
        continue
    ok = user32.SetWindowPos(h, wintypes.HWND(0), w["x"], w["y"], w["w"], w["h"],
                             SWP_NOZORDER | SWP_NOACTIVATE)
    print(f"  hwnd={w['hwnd']} -> ({w['x']},{w['y']}) {w['w']}x{w['h']} ok={bool(ok)}")
print("restore pass done")
