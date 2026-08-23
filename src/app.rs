//! The whole program, shared by both binaries.
//!
//! There are two entry points for the same reason Python ships python.exe and
//! pythonw.exe: a console binary (align-terminals) whose stdout every shell
//! captures and waits for, and a windows-subsystem binary (align-terminalsw)
//! for the taskbar shortcut, which must never flash a console. PowerShell
//! neither waits for nor captures a GUI-subsystem process unless its output
//! is piped, so the console binary is the one scripts should run.
//!
//! The CLI, exit codes, and every summary line are kept byte-identical to the
//! Python oracle (align_terminals.pyw) so the differential probes can diff
//! the two implementations' stdout directly. Only the program name in the
//! usage text differs.

use crate::layout::{layout, Rect};
use crate::snapshot::{self, Entry};
use crate::win::{self, Hwnd};
use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;

const USAGE: &str = "\
usage: align-terminals [--arrange | --restore]

  (no argument)  arrange, or put the windows back when none of them has moved since
                 the last run. This is what the taskbar shortcut uses.
  --arrange      always arrange, never restore.
  --restore      only restore. If a window has moved since the last run, report that
                 and change nothing.
";

#[derive(PartialEq, Clone, Copy)]
enum Mode {
    Toggle,
    Arrange,
    Restore,
}

/// stdout may be an attached console, a pipe, or nothing at all (taskbar
/// launch); a failed write must never crash a run that already moved windows.
/// Line endings are CRLF because the Python oracle prints through text mode,
/// and the differential probes diff the two outputs byte for byte.
fn say(line: &str) {
    let _ = write!(std::io::stdout(), "{line}\r\n");
}

fn emit_usage(to_stderr: bool) {
    let text = USAGE.replace('\n', "\r\n");
    if to_stderr {
        let _ = write!(std::io::stderr(), "{text}");
    } else {
        let _ = write!(std::io::stdout(), "{text}");
    }
}

/// Run the tool and flush; both binaries' main() is just this plus an exit.
pub fn run_and_flush() -> i32 {
    let code = run();
    let _ = std::io::stdout().flush();
    code
}

fn entries_map(entries: &[Entry]) -> BTreeMap<Hwnd, Rect> {
    entries
        .iter()
        .map(|e| {
            let [left, top, width, height] = e.rect;
            (
                e.hwnd as Hwnd,
                Rect {
                    left,
                    top,
                    width,
                    height,
                },
            )
        })
        .collect()
}

fn run() -> i32 {
    // A caller that means one direction says so; only the argument-free run guesses.
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mode = match args.iter().map(String::as_str).collect::<Vec<_>>()[..] {
        ["--arrange"] => Mode::Arrange,
        ["--restore"] => Mode::Restore,
        [] => Mode::Toggle,
        ["--help"] | ["-h"] => {
            emit_usage(false);
            return 0;
        }
        _ => {
            emit_usage(true);
            return 2;
        }
    };

    let targets = win::terminal_windows();
    if targets.is_empty() {
        say("No Windows Terminal window was found; nothing to arrange.");
        return 0;
    }

    // None if any window could not be measured; the run then arranges fresh.
    let measured_now: Option<BTreeMap<Hwnd, Rect>> = targets
        .iter()
        .map(|&hwnd| win::window_rect(hwnd).map(|rect| (hwnd, rect)))
        .collect();

    // Restoring only happens when every window still sits exactly where the
    // last run left it. Anything moved by hand since then means the user is
    // asking for a fresh arrangement, not an undo, so an argument-free run
    // arranges instead. An explicit --restore reports the mismatch rather
    // than quietly doing the opposite.
    let snap = measured_now.as_ref().and_then(|_| snapshot::read());
    let already_arranged = match (&snap, &measured_now) {
        (Some(s), Some(measured)) => &entries_map(&s.arranged) == measured,
        _ => false,
    };

    if mode != Mode::Arrange && already_arranged {
        let s = snap.as_ref().unwrap();
        let previous = entries_map(&s.previous);
        let measured = measured_now.as_ref().unwrap();
        if previous.keys().eq(measured.keys()) {
            let was_iconic: BTreeSet<Hwnd> = s
                .previous
                .iter()
                .filter(|e| e.iconic == Some(true))
                .map(|e| e.hwnd as Hwnd)
                .collect();
            let pairs: Vec<(Hwnd, Rect)> =
                targets.iter().map(|&hwnd| (hwnd, previous[&hwnd])).collect();
            let rejected = win::place(&pairs, false);
            let restored = pairs
                .iter()
                .filter(|&&(hwnd, rect)| win::window_rect(hwnd) == Some(rect))
                .count();
            for &hwnd in &was_iconic {
                win::minimize_window(hwnd);
            }
            let mut summary = format!(
                "Restored {restored} of {} Windows Terminal windows to their previous \
                 positions, measured after the move.",
                pairs.len()
            );
            if !was_iconic.is_empty() {
                summary += &format!(" {} window(s) minimized again.", was_iconic.len());
            }
            if rejected > 0 {
                summary += &format!(" {rejected} SetWindowPos call(s) were rejected.");
            }
            say(&summary);
            return 0;
        }
    }

    if mode == Mode::Restore {
        say(
            "The windows no longer match the last arrangement, so nothing was moved. \
             Run without --restore to arrange them.",
        );
        return 0;
    }

    // A lone window has nothing to be tiled against, so the only thing worth
    // doing is what the arrangement is really for: getting the terminal out
    // from behind whatever is covering it. Its geometry is left untouched.
    if targets.len() == 1 {
        let rejected = win::raise_to_front(&targets);
        win::set_foreground(targets[0]);
        let mut summary = String::from(
            "Only one Windows Terminal window is open; it was brought to the front \
             and left at its current size and position.",
        );
        if rejected > 0 {
            summary += &format!(" {rejected} SetWindowPos call(s) were rejected.");
        }
        say(&summary);
        return 0;
    }

    let mut iconic: BTreeSet<Hwnd> = BTreeSet::new();
    for &hwnd in &targets {
        if win::is_iconic(hwnd) {
            iconic.insert(hwnd);
            win::restore_window(hwnd);
        }
    }

    let Some(area) = win::work_area() else {
        let _ = write!(
            std::io::stderr(),
            "Could not read the primary monitor work area.\r\n"
        );
        return 1;
    };
    let count = targets.len();

    // Measured after the restore above, so a window that was minimized is
    // remembered by the geometry it will have when it is shown again, not by
    // the off-screen rect Windows reports while it is iconic.
    let current: Vec<(Hwnd, Option<Rect>)> = targets
        .iter()
        .map(|&hwnd| (hwnd, win::window_rect(hwnd)))
        .collect();
    let current_map: BTreeMap<Hwnd, Option<Rect>> = current.iter().copied().collect();
    let mut previous_entries: Vec<Entry> = current
        .iter()
        .filter_map(|&(hwnd, rect)| {
            rect.map(|r| Entry {
                hwnd: hwnd as i64,
                rect: [r.left, r.top, r.width, r.height],
                iconic: Some(iconic.contains(&hwnd)),
            })
        })
        .collect();
    // Arranging what is already arranged must not forget where the windows
    // were before the first run. Overwriting here would make a later restore
    // undo nothing.
    if already_arranged {
        let s = snap.as_ref().unwrap();
        let kept = entries_map(&s.previous);
        if kept.keys().copied().collect::<BTreeSet<_>>()
            == targets.iter().copied().collect::<BTreeSet<_>>()
        {
            previous_entries = s.previous.clone();
        }
    }

    // Sort key matching the order layout() emits its rects in: top row first
    // and left to right within a row, so an already arranged set keeps every
    // window in the slot it is in. Sorting by left first would interleave the
    // rows of a split column and shuffle the windows on every run.
    let mut ordered = targets.clone();
    ordered.sort_by_key(|hwnd| {
        let r = current_map[hwnd].unwrap_or(Rect {
            left: 0,
            top: 0,
            width: 0,
            height: 0,
        });
        (r.top, r.left, r.width, r.height)
    });

    let rects = layout(count as i32, area.left, area.top, area.width, area.height);
    let pairs: Vec<(Hwnd, Rect)> = ordered.iter().copied().zip(rects.iter().copied()).collect();

    let rejected = win::place(&pairs, true) + win::raise_to_front(&ordered);

    // Focus follows the frontmost window; refusal is not worth failing over.
    win::set_foreground(*ordered.last().unwrap());

    // SetWindowPos reports success even when the window ends up with different
    // geometry afterwards, so the summary counts measured rects rather than
    // repeating what was requested. What is measured is the drawn rectangle,
    // because that is what the layout asked for. An edge that could not grow
    // leaves the drawn rect short of its slot by the border, so the target to
    // check against is what outset() says is reachable.
    let drawn_after: BTreeMap<Hwnd, Option<Rect>> = pairs
        .iter()
        .map(|&(hwnd, _)| (hwnd, win::content_rect(hwnd)))
        .collect();
    let placed = pairs
        .iter()
        .filter(|&&(hwnd, rect)| drawn_after[&hwnd] == Some(win::outset(hwnd, rect).1))
        .count();

    // The snapshot records window rects instead, since a restore feeds them
    // straight back to SetWindowPos and has to reproduce them exactly.
    let arranged_entries: Vec<Entry> = pairs
        .iter()
        .filter_map(|&(hwnd, _)| {
            win::window_rect(hwnd).map(|r| Entry {
                hwnd: hwnd as i64,
                rect: [r.left, r.top, r.width, r.height],
                iconic: None,
            })
        })
        .collect();
    let remembered = arranged_entries.len() == count
        && previous_entries.len() == count
        && snapshot::write(arranged_entries, previous_entries);

    // Columns, rows and offset describe the layout that was asked for. The
    // sizes are read back off the screen, because those are what a DPI rescale
    // would spoil and what an edge that could not grow makes smaller.
    let lefts: BTreeSet<i32> = rects.iter().map(|r| r.left).collect();
    let columns = lefts.len();
    let rows = rects.iter().map(|r| r.top).collect::<BTreeSet<_>>().len();
    let offset = if columns > 1 {
        let mut it = lefts.iter();
        let first = *it.next().unwrap();
        *it.next().unwrap() - first
    } else {
        0
    };
    let seen: Vec<Rect> = drawn_after.values().copied().flatten().collect();
    let join_px = |values: BTreeSet<i32>| -> String {
        if values.is_empty() {
            "?".to_string()
        } else {
            values
                .iter()
                .map(|v| format!("{v}px"))
                .collect::<Vec<_>>()
                .join("/")
        }
    };
    let widths = join_px(seen.iter().map(|r| r.width).collect());
    let heights = join_px(seen.iter().map(|r| r.height).collect());

    let mut summary = format!(
        "Arranged {placed} of {count} Windows Terminal windows: {columns} column(s), \
         {rows} row(s), width {widths}, offset {offset}px, height {heights}, \
         measured after placement."
    );
    if rejected > 0 {
        summary += &format!(" {rejected} SetWindowPos call(s) were rejected.");
    }
    summary += if remembered {
        " Run again to put them back."
    } else {
        " Previous positions could not be saved, so running again will not restore them."
    };
    say(&summary);
    0
}
