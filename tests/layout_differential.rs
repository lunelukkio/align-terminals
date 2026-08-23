//! The Python implementation is the oracle. tools/gen_layout_fixture.py records
//! its layout() output and this test holds the Rust port to every rect of it.

use align_terminals::layout::{layout, Rect};
use serde::Deserialize;

#[derive(Deserialize)]
struct Case {
    count: i32,
    area: [i32; 4],
    rects: Vec<[i32; 4]>,
}

#[derive(Deserialize)]
struct Fixture {
    cases: Vec<Case>,
}

#[test]
fn layout_matches_the_python_oracle() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/fixtures/layout_cases.json"
    );
    let text = std::fs::read_to_string(path)
        .expect("fixture missing; regenerate with: py -3 tools/gen_layout_fixture.py");
    let fixture: Fixture = serde_json::from_str(&text).unwrap();
    assert!(
        fixture.cases.len() >= 200,
        "suspiciously small fixture; regenerate it"
    );
    for case in &fixture.cases {
        let [left, top, width, height] = case.area;
        let got = layout(case.count, left, top, width, height);
        let want: Vec<Rect> = case
            .rects
            .iter()
            .map(|&[l, t, w, h]| Rect {
                left: l,
                top: t,
                width: w,
                height: h,
            })
            .collect();
        assert_eq!(
            got, want,
            "count {} in area {:?} disagrees with the oracle",
            case.count, case.area
        );
    }
}
