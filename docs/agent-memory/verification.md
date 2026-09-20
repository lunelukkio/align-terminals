# 配置検証の注意点

## 自動検証と実機の境界

- `tests/test_oracle.py`はテスト用Win32応答でPythonの実際の`main()`を検証する。実desktopを操作せず、taskbar・席維持・枚数変更・復元の回帰を検出する。
- `tools/gen_layout_fixture.py`と`tools/gen_placement_fixture.py`がoracleからfixtureを作り、Rustのdifferential testが照合する。policy変更時は対応fixtureも再生成する。
- fixtureではDPIの実挙動は分からない。実機では別倍率のmonitorから移動後の`N of M`、描画下端、隙間0px、繰り返し整列時のwindowごとの位置を別々に測る。
- `tools/placement_probe.py`はtaskbar予約領域と描画rectの内外をread-onlyで測る。未整列の状態で範囲外を報告するのは期待どおりで、配置の失敗とは限らない。
- 2 exeは`tools/deploy.ps1`でrepo rootへcopyされて初めてshortcut側へ反映される。rootのexeはGit対象外で、release buildだけでは更新されない。

## 隔離desktopで0枚になる場合

- 2026-09-20の実測では、権限を上げたprocessも隔離desktop側に残り、通常の列挙はTerminal 0枚・taskbar未取得だった。windowが存在しないと即断できない。
- `tools/placement_probe.py --input-desktop`は、OSが許可する場合に`OpenInputDesktop`と`SetThreadDesktop`で診断threadだけを接続する。表示desktopの切替やwindow移動は行わない。
- この環境の実機試験では子processにthreadの接続先は自動継承されず、`CreateProcessW`の`STARTUPINFO.lpDesktop`指定が必要だった。本番exeへdesktop切替処理を追加したわけではない。
- 実機試験はwindow位置とsnapshotを退避し、試験用snapshotを本番と隔離して行う。終了時にgeometryを戻し、本番snapshotが変更されていないことも確認する。
- z-orderとkeyboard focusは別の確認対象。2026-09-20の試験では別アプリへのfocus移動が拒否されたため、z-orderの前後関係とTOPMOST残留なしを確認した記録として扱う。

## 既存の制約

- 負のxへの復元は混在DPIの座標解釈により完全一致しない場合がある。根拠は`DPI-verification.md`の負座標の節。
- 縦に短い作業領域で多段配置すると、Terminalの最小window高が制約になる可能性がある。実機での下限は未確認。

根拠: `tests/`、`tools/placement_probe.py`、`tools/deploy.ps1`、`DPI-verification.md`、`docs/placement-plan.md`。
