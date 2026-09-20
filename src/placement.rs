//! Placement policy, independent of Win32: reserve the taskbar and keep seats.

use crate::layout::Rect;
use std::collections::{BTreeMap, BTreeSet};

/// Reserve a full taskbar thickness even while its window is off-screen.
/// Edges follow Win32 ABE_LEFT/TOP/RIGHT/BOTTOM (0/1/2/3).
/// Clamp against monitor edges so an existing work-area inset is not counted twice.
pub fn reserve_taskbar(area: Rect, monitor: Rect, edge: u32, thickness: i32) -> Rect {
    let right = |r: Rect| i64::from(r.left) + i64::from(r.width);
    let bottom = |r: Rect| i64::from(r.top) + i64::from(r.height);
    if thickness <= 0
        || area.width <= 0
        || area.height <= 0
        || monitor.width <= 0
        || monitor.height <= 0
        || area.left < monitor.left
        || area.top < monitor.top
        || right(area) > right(monitor)
        || bottom(area) > bottom(monitor)
    {
        return area;
    }
    let (mut left, mut top, mut r, mut b) = (
        i64::from(area.left),
        i64::from(area.top),
        right(area),
        bottom(area),
    );
    let t = i64::from(thickness);
    match edge {
        0 => left = left.max(i64::from(monitor.left) + t),
        1 => top = top.max(i64::from(monitor.top) + t),
        2 => r = r.min(right(monitor) - t),
        3 => b = b.min(bottom(monitor) - t),
        _ => return area,
    }
    if left >= r || top >= b {
        return area;
    }
    Rect {
        left: left as i32,
        top: top as i32,
        width: (r - left) as i32,
        height: (b - top) as i32,
    }
}

fn distance(a: Rect, b: Rect) -> i128 {
    // Doubled centers preserve half pixels without float rounding or overflow.
    let dx =
        2 * (i128::from(a.left) - i128::from(b.left)) + i128::from(a.width) - i128::from(b.width);
    let dy =
        2 * (i128::from(a.top) - i128::from(b.top)) + i128::from(a.height) - i128::from(b.height);
    dx * dx + dy * dy
}

/// Rectangular Hungarian assignment: every anchor gets one distinct slot.
/// Stable input order and strict comparisons make equal-cost choices repeatable.
fn nearest_slots(anchors: &[Rect], slots: &[Rect]) -> Vec<usize> {
    let (n, m) = (anchors.len(), slots.len());
    assert!(n <= m);
    let mut u = vec![0i128; n + 1];
    let mut v = vec![0i128; m + 1];
    let mut owner = vec![0usize; m + 1];
    let mut via = vec![0usize; m + 1];
    for row in 1..=n {
        owner[0] = row;
        let mut col = 0;
        let mut best = vec![i128::MAX / 4; m + 1];
        let mut used = vec![false; m + 1];
        loop {
            used[col] = true;
            let active = owner[col];
            let (mut delta, mut next) = (i128::MAX / 4, 0);
            for j in 1..=m {
                if !used[j] {
                    let cost = distance(anchors[active - 1], slots[j - 1]) - u[active] - v[j];
                    if cost < best[j] {
                        best[j] = cost;
                        via[j] = col;
                    }
                    if best[j] < delta {
                        delta = best[j];
                        next = j;
                    }
                }
            }
            for j in 0..=m {
                if used[j] {
                    u[owner[j]] += delta;
                    v[j] -= delta;
                } else {
                    best[j] -= delta;
                }
            }
            col = next;
            if owner[col] == 0 {
                break;
            }
        }
        while col != 0 {
            let before = via[col];
            owner[col] = owner[before];
            col = before;
        }
    }
    let mut result = vec![0; n];
    for j in 1..=m {
        if owner[j] != 0 {
            result[owner[j] - 1] = j - 1;
        }
    }
    result
}

/// Return window handles in slot order, not enumeration or foreground order.
/// `previous` is the last snapshot's arranged list, already in placement order.
/// Survivors choose first; newly opened windows use the remaining slots.
pub fn assign_slots(
    current: &[(isize, Rect)],
    previous: &[(isize, Rect)],
    slots: &[Rect],
) -> Vec<isize> {
    assert_eq!(current.len(), slots.len());
    let current_map: BTreeMap<isize, Rect> = current.iter().copied().collect();
    let mut seen = BTreeSet::new();
    let known: Vec<(isize, Rect)> = previous
        .iter()
        .copied()
        .filter(|&(hwnd, r)| {
            current_map.contains_key(&hwnd) && r.width > 0 && r.height > 0 && seen.insert(hwnd)
        })
        .collect();
    if previous.len() == slots.len() && known.len() == slots.len() {
        return known.iter().map(|&(hwnd, _)| hwnd).collect();
    }
    let mut new: Vec<(isize, Rect)> = current
        .iter()
        .copied()
        .filter(|(hwnd, _)| !seen.contains(hwnd))
        .collect();
    new.sort_by_key(|&(hwnd, r)| (r.top, r.left, r.width, r.height, hwnd));
    let mut result = vec![0; slots.len()];
    let mut available: Vec<usize> = (0..slots.len()).collect();
    for group in [&known, &new] {
        let anchors: Vec<Rect> = group.iter().map(|&(_, r)| r).collect();
        let free: Vec<Rect> = available.iter().map(|&i| slots[i]).collect();
        let chosen = nearest_slots(&anchors, &free);
        let mut taken = BTreeSet::new();
        for (&(hwnd, _), &index) in group.iter().zip(&chosen) {
            let slot = available[index];
            result[slot] = hwnd;
            taken.insert(slot);
        }
        available.retain(|i| !taken.contains(i));
    }
    result
}
