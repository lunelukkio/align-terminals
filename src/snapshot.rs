//! Where the pre-arrangement positions are remembered between runs.
//!
//! The file is shared with the Python oracle: same path, same schema, so
//! either implementation can restore what the other arranged. Snapshot rects
//! are window rects (GetWindowRect), not drawn rects, because a restore feeds
//! them straight back to SetWindowPos and has to reproduce them exactly.

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Bumped whenever the snapshot layout changes, so an old file is ignored
/// rather than misread into a restore that moves windows somewhere unexpected.
pub const SNAPSHOT_VERSION: u32 = 1;

#[derive(Serialize, Deserialize, Clone)]
pub struct Entry {
    pub hwnd: i64,
    /// (left, top, width, height), same order the Python oracle writes.
    pub rect: [i32; 4],
    /// Present on "previous" entries; "arranged" entries never carry it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub iconic: Option<bool>,
}

#[derive(Serialize, Deserialize)]
pub struct Snapshot {
    pub version: u32,
    pub arranged: Vec<Entry>,
    pub previous: Vec<Entry>,
}

pub fn path() -> PathBuf {
    let base = std::env::var_os("LOCALAPPDATA")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));
    base.join("align-terminals").join("last_layout.json")
}

/// A file that is missing, malformed, or from another version reads as no
/// snapshot at all, matching the oracle's tolerance: the run then arranges
/// instead of guessing at a restore.
pub fn read() -> Option<Snapshot> {
    let text = std::fs::read_to_string(path()).ok()?;
    let snapshot: Snapshot = serde_json::from_str(&text).ok()?;
    (snapshot.version == SNAPSHOT_VERSION).then_some(snapshot)
}

pub fn write(arranged: Vec<Entry>, previous: Vec<Entry>) -> bool {
    let snapshot = Snapshot {
        version: SNAPSHOT_VERSION,
        arranged,
        previous,
    };
    let file = path();
    let Some(dir) = file.parent() else {
        return false;
    };
    if std::fs::create_dir_all(dir).is_err() {
        return false;
    }
    let Ok(text) = serde_json::to_string_pretty(&snapshot) else {
        return false;
    };
    std::fs::write(file, text).is_ok()
}
