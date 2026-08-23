//! Windows-subsystem binary for the taskbar shortcut: launching it never
//! flashes a console. Run from a shell it adopts that shell's console so the
//! summary still appears, but PowerShell will not wait for it or capture it
//! un-piped; scripts should run the console binary instead.
#![windows_subsystem = "windows"]

fn main() {
    // Before the first stdout use: Rust caches the handle it finds.
    align_terminals::win::attach_parent_console();
    std::process::exit(align_terminals::app::run_and_flush());
}
