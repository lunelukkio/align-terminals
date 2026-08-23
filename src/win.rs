//! Thin wrappers over the Win32 calls the tool needs.
//!
//! Everything here mirrors the Python oracle's ctypes usage. The comments
//! carry the traps that are invisible in the code itself; every one of them
//! was found by measuring a real desktop, so do not simplify any of this
//! without re-measuring (AGENTS.md lists the procedure).

use crate::layout::Rect;
use windows_sys::Win32::Foundation::{CloseHandle, HWND, LPARAM, POINT, RECT};
use windows_sys::Win32::Graphics::Gdi::{ClientToScreen, MonitorFromPoint, MONITOR_DEFAULTTONULL};
use windows_sys::Win32::System::Console::{AttachConsole, ATTACH_PARENT_PROCESS};
use windows_sys::Win32::System::Threading::{
    OpenProcess, QueryFullProcessImageNameW, PROCESS_QUERY_LIMITED_INFORMATION,
};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetClassNameW, GetClientRect, GetWindowRect, GetWindowThreadProcessId, IsIconic,
    IsWindowVisible, SetForegroundWindow, SetWindowPos, ShowWindow, SystemParametersInfoW,
    HWND_NOTOPMOST, HWND_TOP, HWND_TOPMOST, SPI_GETWORKAREA, SWP_NOACTIVATE, SWP_NOMOVE,
    SWP_NOSIZE, SWP_NOZORDER, SW_MINIMIZE, SW_RESTORE,
};

const TERMINAL_CLASS: &str = "CASCADIA_HOSTING_WINDOW_CLASS";
const TERMINAL_PROCESS: &str = "windowsterminal.exe";

/// Window handles travel as isize so they can be hashed, ordered, and written
/// to the snapshot the same way the Python oracle writes int(hwnd).
pub type Hwnd = isize;

fn raw(hwnd: Hwnd) -> HWND {
    hwnd as HWND
}

/// Adopt the parent's console when there is one.
///
/// The exe is a windows-subsystem binary so a taskbar launch never flashes a
/// console window; run from a shell instead, this attaches to that shell's
/// console and the summary reaches it. AttachConsole leaves redirected std
/// handles (a pipe, a file) alone, so captured output keeps working. Must run
/// before the first stdout use, because Rust caches the handle.
pub fn attach_parent_console() {
    unsafe { AttachConsole(ATTACH_PARENT_PROCESS) };
}

fn class_name(hwnd: HWND) -> String {
    let mut buffer = [0u16; 256];
    let length = unsafe { GetClassNameW(hwnd, buffer.as_mut_ptr(), buffer.len() as i32) };
    if length <= 0 {
        return String::new();
    }
    String::from_utf16_lossy(&buffer[..length as usize])
}

fn process_name(hwnd: HWND) -> String {
    let mut pid = 0u32;
    unsafe { GetWindowThreadProcessId(hwnd, &mut pid) };
    if pid == 0 {
        return String::new();
    }
    let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
    if handle.is_null() {
        return String::new();
    }
    let mut buffer = [0u16; 1024];
    let mut size = buffer.len() as u32;
    let ok = unsafe { QueryFullProcessImageNameW(handle, 0, buffer.as_mut_ptr(), &mut size) };
    unsafe { CloseHandle(handle) };
    if ok == 0 {
        return String::new();
    }
    let path = String::from_utf16_lossy(&buffer[..size as usize]);
    path.rsplit('\\').next().unwrap_or("").to_lowercase()
}

/// Every Windows Terminal top-level window, in EnumWindows order.
pub fn terminal_windows() -> Vec<Hwnd> {
    unsafe extern "system" fn collect(hwnd: HWND, lparam: LPARAM) -> i32 {
        let targets = &mut *(lparam as *mut Vec<Hwnd>);
        if class_name(hwnd) != TERMINAL_CLASS {
            return 1;
        }
        // A minimized window is not "visible" for layout purposes but must
        // still be collected, so visibility only skips hidden helper windows.
        if IsWindowVisible(hwnd) == 0 && IsIconic(hwnd) == 0 {
            return 1;
        }
        if process_name(hwnd) != TERMINAL_PROCESS {
            return 1;
        }
        targets.push(hwnd as Hwnd);
        1
    }

    let mut targets: Vec<Hwnd> = Vec::new();
    unsafe { EnumWindows(Some(collect), &mut targets as *mut Vec<Hwnd> as LPARAM) };
    targets
}

pub fn window_rect(hwnd: Hwnd) -> Option<Rect> {
    let mut r = RECT {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
    };
    (unsafe { GetWindowRect(raw(hwnd), &mut r) } != 0).then(|| Rect {
        left: r.left,
        top: r.top,
        width: r.right - r.left,
        height: r.bottom - r.top,
    })
}

/// Where the terminal actually draws, in screen coordinates.
///
/// This is the rectangle a person sees. It is smaller than window_rect, which
/// also covers an invisible resize border, and it is what the layout lines up.
pub fn content_rect(hwnd: Hwnd) -> Option<Rect> {
    let mut client = RECT {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
    };
    if unsafe { GetClientRect(raw(hwnd), &mut client) } == 0 {
        return None;
    }
    let mut origin = POINT { x: 0, y: 0 };
    if unsafe { ClientToScreen(raw(hwnd), &mut origin) } == 0 {
        return None;
    }
    Some(Rect {
        left: origin.x,
        top: origin.y,
        width: client.right,
        height: client.bottom,
    })
}

fn monitor_at(x: i32, y: i32) -> *mut core::ffi::c_void {
    unsafe { MonitorFromPoint(POINT { x, y }, MONITOR_DEFAULTTONULL) }
}

/// Grow a target rect by this window's invisible border.
///
/// SetWindowPos positions the window rect, but the border it includes is not
/// drawn, so windows placed edge to edge by those coordinates show a gap of
/// two borders between them. Asking for a correspondingly larger rect puts the
/// drawn edges where the layout wants them and closes the gap.
///
/// The border is measured per window and per pass rather than assumed, because
/// it is reported in the coordinate space of whichever monitor the window is
/// on. GetClientRect + ClientToScreen report in this process's own space, so
/// no DPI conversion enters the code.
///
/// An edge that would grow onto a neighbouring monitor is left alone. This
/// process is system-DPI-aware, so coordinates outside the primary monitor
/// are read in that monitor's scale and such a request lands somewhere else
/// entirely: asking for left -7 next to a 150% monitor puts the window at -5.
/// Growing into empty space past the end of the desktop has no such problem
/// and is allowed, which is what keeps the outermost edges flush.
///
/// Returns the rect to ask SetWindowPos for together with the drawn rect that
/// request will really produce. The two disagree wherever an edge could not
/// grow, because the border keeps its size and eats into the slot instead.
pub fn outset(hwnd: Hwnd, rect: Rect) -> (Rect, Rect) {
    let (Some(frame), Some(content)) = (window_rect(hwnd), content_rect(hwnd)) else {
        return (rect, rect);
    };
    let home = monitor_at(rect.left + rect.width / 2, rect.top + rect.height / 2);
    let reachable = |x: i32, y: i32| {
        let found = monitor_at(x, y);
        found.is_null() || found == home
    };

    let border_left = content.left - frame.left;
    let border_top = content.top - frame.top;
    let border_right = (frame.left + frame.width) - (content.left + content.width);
    let border_bottom = (frame.top + frame.height) - (content.top + content.height);

    let mut pad_left = border_left;
    let mut pad_top = border_top;
    let mut pad_right = border_right;
    let mut pad_bottom = border_bottom;
    if pad_left != 0 && !reachable(rect.left - pad_left, rect.top) {
        pad_left = 0;
    }
    if pad_top != 0 && !reachable(rect.left, rect.top - pad_top) {
        pad_top = 0;
    }
    if pad_right != 0 && !reachable(rect.left + rect.width + pad_right - 1, rect.top) {
        pad_right = 0;
    }
    if pad_bottom != 0 && !reachable(rect.left, rect.top + rect.height + pad_bottom - 1) {
        pad_bottom = 0;
    }

    let request = Rect {
        left: rect.left - pad_left,
        top: rect.top - pad_top,
        width: rect.width + pad_left + pad_right,
        height: rect.height + pad_top + pad_bottom,
    };
    let drawn = Rect {
        left: request.left + border_left,
        top: request.top + border_top,
        width: request.width - border_left - border_right,
        height: request.height - border_top - border_bottom,
    };
    (request, drawn)
}

/// Apply every geometry and count the calls Windows rejected.
///
/// The final geometry is always asked for twice. A window that crosses a
/// monitor DPI boundary receives WM_DPICHANGED once the move lands and
/// rescales itself by the destination/source DPI ratio, overwriting the size
/// that pass asked for. The repeat crosses no boundary, so its size holds.
/// This is not a converge-by-retry loop: the repeat is what makes the size
/// stick and a further pass changes nothing. Restoring crosses the boundary
/// the other way and needs the repeat just as much.
///
/// With fill_gaps the pairs carry the rect the drawn window should end up
/// with, and a plain pass runs first. Its only job is to land every window on
/// the target monitor, because until then the border is reported in the old
/// monitor's scale, and for a moment after the rescale it is still off by a
/// pixel. Only the two grown passes measure a border worth trusting, and the
/// second of them is what corrects the first.
///
/// Without fill_gaps the pairs carry window rects to reproduce exactly, which
/// is what a restore wants.
///
/// Geometry only. Z-order is left alone here so a restore cannot reshuffle
/// it, and so raising stays in raise_to_front where it belongs.
pub fn place(pairs: &[(Hwnd, Rect)], fill_gaps: bool) -> u32 {
    let mut rejected = 0;
    let flags = SWP_NOZORDER | SWP_NOACTIVATE;
    let passes: &[bool] = if fill_gaps {
        &[false, true, true]
    } else {
        &[false, false]
    };
    for &grow in passes {
        for &(hwnd, rect) in pairs {
            let r = if grow { outset(hwnd, rect).0 } else { rect };
            if unsafe { SetWindowPos(raw(hwnd), HWND_TOP, r.left, r.top, r.width, r.height, flags) }
                == 0
            {
                rejected += 1;
            }
        }
    }
    rejected
}

/// Lift each window to the front of the ordinary band, in the order given.
///
/// Asking for HWND_TOP is not enough. A process that does not own the
/// foreground window may not place another window above it, and Windows
/// clamps the request to just underneath instead of failing, so SetWindowPos
/// still reports success. Launched from a taskbar shortcut while a browser is
/// in front, that leaves every terminal except the one that later takes focus
/// behind the browser.
///
/// Joining and leaving the topmost band is not clamped that way: HWND_TOPMOST
/// puts the window above every ordinary window, and HWND_NOTOPMOST drops it
/// back to the front of the ordinary band. Doing that left to right leaves
/// the rightmost window in front, the same order the placement asks for.
///
/// Geometry is untouched on purpose. A z-order-only call cannot trigger
/// WM_DPICHANGED, so this pass stays clear of the placement passes above.
pub fn raise_to_front(hwnds: &[Hwnd]) -> u32 {
    let mut rejected = 0;
    let flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE;
    for &hwnd in hwnds {
        for insert_after in [HWND_TOPMOST, HWND_NOTOPMOST] {
            if unsafe { SetWindowPos(raw(hwnd), insert_after, 0, 0, 0, 0, flags) } == 0 {
                rejected += 1;
            }
        }
    }
    rejected
}

pub fn is_iconic(hwnd: Hwnd) -> bool {
    unsafe { IsIconic(raw(hwnd)) != 0 }
}

pub fn restore_window(hwnd: Hwnd) {
    unsafe { ShowWindow(raw(hwnd), SW_RESTORE) };
}

pub fn minimize_window(hwnd: Hwnd) {
    unsafe { ShowWindow(raw(hwnd), SW_MINIMIZE) };
}

/// Windows may refuse this while another process holds the foreground lock,
/// which is not worth failing the run over: raise_to_front has already put
/// every terminal in front either way.
pub fn set_foreground(hwnd: Hwnd) {
    unsafe { SetForegroundWindow(raw(hwnd)) };
}

pub fn work_area() -> Option<Rect> {
    let mut r = RECT {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
    };
    let ok = unsafe {
        SystemParametersInfoW(SPI_GETWORKAREA, 0, &mut r as *mut RECT as *mut core::ffi::c_void, 0)
    };
    (ok != 0).then(|| Rect {
        left: r.left,
        top: r.top,
        width: r.right - r.left,
        height: r.bottom - r.top,
    })
}
