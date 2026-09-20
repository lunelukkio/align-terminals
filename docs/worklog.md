# 作業ログ (worklog)

## 全体の要点

- 本番はRustの2 exe、Python版はoracle。taskbarの表示領域を確保し、同じwindowの席を維持する。

## 前回の作業（2026-09-20）

- Rust/Python両方の修正、test・fixture・probe追加、2 exeへの配備を完了。根拠と実測は`docs/placement-plan.md`。
- Python 14 test、Rust 6 test（fixture計551 case）、formatとdiffの検証が通過。taskbar・再整列・枚数増減・混在DPI・相互復元を実機確認し、ユーザーの確認も完了した。
- worklogとproject memoryを作成し、既存handoffを整理した。実装commit `bbf683b`を`origin/main`へpush済み。
