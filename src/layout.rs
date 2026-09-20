//! The tiling arithmetic, pure so it runs under `cargo test` without a desktop.
//!
//! Ported from `layout()` in align_terminals.pyw, which remains the oracle:
//! tools/gen_layout_fixture.py records the oracle's output and
//! tests/layout_differential.rs holds this port to every rect of it.

/// Windows a row holds before the layout adds another row.
pub const MAX_PER_ROW: i32 = 5;
/// Columns that still tile without overlapping. Past this the width stops
/// shrinking and the columns overlap instead, which is what keeps each window
/// wide enough to read.
pub const MAX_TILED_COLUMNS: i32 = 4;

/// A window rectangle in the coordinate space this process sees (virtualized
/// logical pixels; the manifest pins the process to DPI-unaware so
/// this space matches the Python oracle's).
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Debug)]
pub struct Rect {
    pub left: i32,
    pub top: i32,
    pub width: i32,
    pub height: i32,
}

/// Return one rect per window, in placement order.
///
/// Placement order is also z-order: each rect is raised in turn, so a window
/// overlaps every window listed before it. The order is the reading order of
/// the grid: any full-height column first, then the top row left to right,
/// then the row below it. The placement policy assigns handles to these
/// slots using the saved arrangement, independently of outer frame borders.
///
/// A row holds at most MAX_PER_ROW windows. Within that, count / rows columns
/// each hold one window per row and the count % rows windows left over become
/// full-height columns on the left. Column width is the work area divided by
/// the column count, but never by more than MAX_TILED_COLUMNS: up to four
/// columns tile exactly, a fifth keeps the quarter width and the columns
/// overlap evenly instead.
///
/// A lone window is not placed at all. Returning nothing here lets the caller
/// raise it and leave its geometry untouched.
pub fn layout(
    count: i32,
    area_left: i32,
    area_top: i32,
    area_width: i32,
    area_height: i32,
) -> Vec<Rect> {
    if count <= 1 {
        return Vec::new();
    }

    // Every division below has non-negative operands, so Rust's truncating
    // division agrees with the floor division the Python oracle uses.
    let rows = (count + MAX_PER_ROW - 1) / MAX_PER_ROW;
    // Windows that do not divide evenly into rows stand full height on the left.
    let tall = count % rows;
    let columns = tall + count / rows;

    let width = area_width / columns.min(MAX_TILED_COLUMNS);
    let offset = if columns > 1 {
        (area_width - width) / (columns - 1)
    } else {
        0
    };
    let row_height = area_height / rows;

    let mut rects: Vec<Rect> = (0..tall)
        .map(|column| Rect {
            left: area_left + column * offset,
            top: area_top,
            width,
            height: area_height,
        })
        .collect();
    for row in 0..rows {
        // The last row takes the rounding remainder so the grid reaches the bottom.
        let height = if row == rows - 1 {
            area_height - row * row_height
        } else {
            row_height
        };
        for column in tall..columns {
            rects.push(Rect {
                left: area_left + column * offset,
                top: area_top + row * row_height,
                width,
                height,
            });
        }
    }
    rects
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Shape summary of a layout: (columns, rows, width, offset, tall columns).
    fn shape(rects: &[Rect], area_height: i32) -> (usize, usize, i32, i32, usize) {
        let mut lefts: Vec<i32> = rects.iter().map(|r| r.left).collect();
        lefts.sort();
        lefts.dedup();
        let mut tops: Vec<i32> = rects.iter().map(|r| r.top).collect();
        tops.sort();
        tops.dedup();
        let offset = if lefts.len() > 1 {
            lefts[1] - lefts[0]
        } else {
            0
        };
        let tall = if tops.len() > 1 {
            rects.iter().filter(|r| r.height == area_height).count()
        } else {
            0
        };
        (lefts.len(), tops.len(), rects[0].width, offset, tall)
    }

    /// The counts the user specified, from DPI-verification.md's table.
    #[test]
    fn the_specified_counts_keep_their_shape() {
        let cases: &[(i32, (usize, usize, i32, i32, usize))] = &[
            (2, (2, 1, 960, 960, 0)),
            (3, (3, 1, 640, 640, 0)),
            (4, (4, 1, 480, 480, 0)),
            (5, (5, 1, 480, 360, 0)),
            (6, (3, 2, 640, 640, 0)),
            (7, (4, 2, 480, 480, 1)),
            (8, (4, 2, 480, 480, 0)),
            (9, (5, 2, 480, 360, 1)),
            (10, (5, 2, 480, 360, 0)),
            (11, (5, 3, 480, 360, 2)),
        ];
        for &(count, expected) in cases {
            let rects = layout(count, 0, 0, 1920, 1040);
            assert_eq!(rects.len(), count as usize);
            assert_eq!(shape(&rects, 1040), expected, "count {count}");
        }
    }

    #[test]
    fn a_lone_window_is_not_placed() {
        assert!(layout(0, 0, 0, 1920, 1040).is_empty());
        assert!(layout(1, 0, 0, 1920, 1040).is_empty());
    }

    #[test]
    fn the_grid_reaches_every_edge_and_keeps_reading_order() {
        for count in 2..=48 {
            let (l, t, w, h) = (0, 32, 1920, 1008);
            let rects = layout(count, l, t, w, h);
            assert_eq!(rects.len(), count as usize);
            for r in &rects {
                assert!(r.left >= l && r.left + r.width <= l + w, "count {count}");
                assert!(r.top >= t && r.top + r.height <= t + h, "count {count}");
                assert!(r.width > 0 && r.height > 0, "count {count}");
            }
            // The offset is floored, so the rightmost column can stop short of
            // the right edge by up to one pixel per column gap (the Python
            // oracle rounds the same way); it must never stick out.
            let rightmost = rects.iter().map(|r| r.left + r.width).max().unwrap();
            let columns = rects.iter().map(|r| r.left).collect::<Vec<_>>().len() as i32;
            assert!(
                rightmost <= l + w && rightmost > l + w - columns,
                "count {count}: rightmost edge {rightmost} strays from {}",
                l + w
            );
            assert_eq!(
                rects.iter().map(|r| r.top + r.height).max(),
                Some(t + h),
                "count {count}: bottom row must reach the bottom edge"
            );
            // Re-arranging sorts windows by (top, left, width, height); that
            // must reproduce emission order or slots get shuffled.
            let mut sorted = rects.clone();
            sorted.sort_by_key(|r| (r.top, r.left, r.width, r.height));
            assert_eq!(sorted, rects, "count {count}: reading order must be stable");
        }
    }
}
