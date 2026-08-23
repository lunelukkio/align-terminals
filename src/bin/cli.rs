//! Console binary: the one scripts and shells should run. Its stdout is a real
//! console handle (or whatever the shell redirected), so every shell captures
//! it and waits for it.

fn main() {
    std::process::exit(align_terminals::app::run_and_flush());
}
