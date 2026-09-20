//! Policy differential, including count changes and DPI-sized taskbar insets.

use align_terminals::layout::Rect;
use align_terminals::placement::{assign_slots, reserve_taskbar};
use serde::Deserialize;

#[derive(Deserialize)]
struct Assignment {
    current: Vec<(isize, [i32; 4])>,
    previous: Vec<(isize, [i32; 4])>,
    slots: Vec<[i32; 4]>,
    ordered: Vec<isize>,
}

#[derive(Deserialize)]
struct Taskbar {
    area: [i32; 4],
    monitor: [i32; 4],
    edge: u32,
    thickness: i32,
    expected: [i32; 4],
}

#[derive(Deserialize)]
struct Fixture {
    assignments: Vec<Assignment>,
    taskbars: Vec<Taskbar>,
}

fn rect([left, top, width, height]: [i32; 4]) -> Rect {
    Rect {
        left,
        top,
        width,
        height,
    }
}

fn fixture() -> Fixture {
    serde_json::from_str(include_str!("fixtures/placement_cases.json")).unwrap()
}

#[test]
fn window_assignment_matches_python_for_add_remove_restore_and_ties() {
    let data = fixture();
    assert!(data.assignments.len() >= 180);
    for (i, case) in data.assignments.iter().enumerate() {
        let current: Vec<_> = case.current.iter().map(|&(h, r)| (h, rect(r))).collect();
        let previous: Vec<_> = case.previous.iter().map(|&(h, r)| (h, rect(r))).collect();
        let slots: Vec<_> = case.slots.iter().copied().map(rect).collect();
        assert_eq!(
            assign_slots(&current, &previous, &slots),
            case.ordered,
            "case {i}"
        );
    }
}

#[test]
fn taskbar_reservation_matches_python_for_every_edge() {
    let data = fixture();
    assert!(data.taskbars.len() >= 100);
    for (i, case) in data.taskbars.iter().enumerate() {
        assert_eq!(
            reserve_taskbar(
                rect(case.area),
                rect(case.monitor),
                case.edge,
                case.thickness
            ),
            rect(case.expected),
            "case {i}"
        );
    }
}
