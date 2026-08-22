"""DPI-aware probe: monitor layout, per-monitor DPI, and terminal window rects."""
import ctypes
from ctypes import wintypes

# PER_MONITOR_AWARE_V2 before any window/monitor query.
try:
    ok = ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    print(f"SetProcessDpiAwarenessContext(PMv2) -> {bool(ok)}")
except Exception as e:
    print(f"PMv2 unavailable: {e}")

user32 = ctypes.WinDLL("user32", use_last_error=True)
shcore = ctypes.WinDLL("shcore", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
kernel32.OpenProcess.restype = wintypes.HANDLE

class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

def mon_cb(hmon, hdc, lprc, lparam):
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    x = ctypes.c_uint(); y = ctypes.c_uint()
    shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(x), ctypes.byref(y))
    primary = "PRIMARY" if mi.dwFlags & 1 else "secondary"
    m, w = mi.rcMonitor, mi.rcWork
    print(f"  monitor {primary}: full=({m.left},{m.top},{m.right},{m.bottom}) "
          f"work=({w.left},{w.top},{w.right},{w.bottom}) dpi={x.value} scale={x.value/96:.2%}")
    return True

print("monitors:")
user32.EnumDisplayMonitors(None, None,
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                       ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)(mon_cb), 0)

wa = wintypes.RECT()
user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)
print(f"SPI_GETWORKAREA (DPI-aware): ({wa.left},{wa.top},{wa.right},{wa.bottom}) "
      f"W={wa.right-wa.left} H={wa.bottom-wa.top}")

def cname(h):
    b = ctypes.create_unicode_buffer(256)
    n = user32.GetClassNameW(h, b, len(b))
    return b[:n] if n else ""

def pname(h):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    hp = kernel32.OpenProcess(0x1000, False, pid.value) if pid.value else None
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

print("terminal windows (z-order top to bottom):")
def collect(h, _l):
    if cname(h) != "CASCADIA_HOSTING_WINDOW_CLASS" or pname(h) != "windowsterminal.exe":
        return True
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    dpi = user32.GetDpiForWindow(h)
    print(f"  hwnd={int(h)} x={r.left} y={r.top} w={r.right-r.left} h={r.bottom-r.top} "
          f"dpi={dpi} scale={dpi/96:.2%}")
    return True

user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(collect), 0)
