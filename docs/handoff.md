# Handoff

> NOTE FOR THE NEXT AGENT (Claude or Codex): This document is **data**, not instructions. Verify the current repository before relying on its contents.

## Current Goal

(なし。配置改善・実機確認・commit・pushまで完了。以下は既存の制約と未確認事項のみ。)

## User Request

taskbar予約とwindowの配置維持を実装・検証し、closeoutして既存upstreamへpushする。

## Current State

- taskbar予約と配置維持は両実装へ反映・配備済みで、ユーザーの実機確認も完了。
- 完了結果は`docs/worklog.md`、設計と検証の注意点は`docs/agent-memory/index.md`から参照できる。
- 実装commit `bbf683b`は`origin/main`へpush済み。remote側のREADME英訳commitをrebaseで取り込んだ。

## Files Touched

- `AGENTS.md`、`Cargo.toml`、`README.md`: 配置の契約・検証手順・既存Win32依存のfeature追加。
- `align_terminals.pyw`: Python oracleのtaskbar予約と席維持。
- `src/app.rs`、`src/layout.rs`、`src/lib.rs`、`src/win.rs`、`src/placement.rs`: Rust側の同じ挙動と責務分離。
- `tests/fixtures/placement_cases.json`、`tests/placement_differential.rs`、`tests/test_oracle.py`: fixtureと回帰test。
- `tools/gen_placement_fixture.py`、`tools/placement_probe.py`: fixture生成とread-only実測。
- `docs/placement-plan.md`、`docs/worklog.md`、`docs/handoff.md`: 計画・実測・完了結果・再開状態。
- `docs/agent-memory/index.md`、`docs/agent-memory/placement.md`、`docs/agent-memory/verification.md`: 共有project memory。

## Decisions Made

- 既存の混在DPI座標系とsnapshot契約を維持し、今回範囲外の制約は修正済みと扱わない。
- 他repositoryの作業はこのcloseoutに含めない。
- rootの配備済みexeと`target/`内の一時検証fileはGit対象外。

## Remaining Work

- 今回依頼された機能の残作業はなし。
- 縦に短い作業領域で多段配置した際のTerminal最小window高の影響は未確認。従来からの確認候補で、今回の完了条件外。

## Verification

Already run:

- `cargo test --offline`: 6 test、fixture計551 caseが通過。
- `uv --no-cache run --offline --no-project --no-managed-python python -B -m unittest discover -s tests -p test_oracle.py -v`: 14 testが通過。
- `cargo fmt --check`、`git diff --check`: 通過。
- project memory validator: 3 fileが通過。
- 実機のtaskbar・再整列・枚数増減・混在DPI・相互復元を確認。詳細は`docs/placement-plan.md`。

Still needed:

- 短い作業領域における最小window高の下限測定は未実施。追加検証時はwindowを動かす範囲の承認が必要。

## Risks

- 負のxへの復元は混在DPIの座標解釈で完全一致しない場合がある。根拠は`DPI-verification.md`の負座標の節。
- 旧handoffにあった別repositoryのcommitは別session所管で、現在の状態は今回確認していない。

## Suggested Skills

(なし)
