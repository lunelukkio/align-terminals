//! Tile Windows Terminal windows across the primary monitor work area.
//!
//! A port of align_terminals.pyw. The Python implementation stays in the
//! repository as the behavioural oracle: its layout() output feeds the
//! differential test, and the real-desktop probes in tools/ compare the two
//! implementations. A behaviour change goes into both or neither.

#[cfg(windows)]
pub mod app;
pub mod layout;
pub mod placement;
pub mod snapshot;
#[cfg(windows)]
pub mod win;
