# handoff: align-terminals

2026-08-22作成。ai-dotfilesからこのprojectを切り出したsessionからの引き継ぎ。

## このprojectは何か

Windows Terminalのwindowを、primary monitor上で左から右へcascade配置する単体tool。
並行して動かしているagent sessionを一望するために使う。

起動経路は2つある。**どちらも同じ`align_terminals.pyw`を使う。**

1. **taskbarのshortcut** — clickで即実行。console windowを出さないため拡張子が`.pyw`。
   （shortcut自体はまだ作っていない。ユーザーが後で置く予定）
2. **AI経由** — ai-dotfilesの`align-terminals` Skillがこのfileを呼ぶ。

## file構成

| path | 役割 |
|---|---|
| `align_terminals.pyw` | 本体。標準libraryのctypesだけ。外部依存なし |
| `DPI-verification.md` | **先に読むこと。** 実機検証の記録と、two-passを消してはいけない理由 |
| `tools/dpi_probe.py` | DPI-awareな観測。monitor構成、per-monitor DPI、各windowの実測rect |
| `tools/snapshot_rects.py` | 実行前のwindow座標をJSONへ保存 |
| `tools/restore_rects.py` | snapshotから復元。検証の開始状態を作り直すのに使う |

git repositoryにしてある（2026-08-22、branchは`main`、remoteは未設定）。
`.gitignore`はroot直下の`*.json`を除外するので、検証で作るsnapshotは追跡されない。

## 直前のsessionでやったこと

ai-dotfilesのmanaged Skillとして実機動作確認をしたところ、混在DPI環境で崩れるbugが出たので
修正し、そのうえでこのprojectへ独立させた。

- **DPI境界を跨ぐwindowのサイズが崩れるbugを修正した。** `SetWindowPos`で移動した直後に
  Windows Terminalが`WM_DPICHANGED`を受けて自分を再スケールし、指定サイズを上書きしていた。
  同じgeometryを2周適用することで解決。詳細と実測値は`DPI-verification.md`にある。
- **summary行を実測ベースにした。** 以前は要求値をそのままprintしていた。bugの最中、
  `SetWindowPos`は5回ともTRUEを返しながらサイズは崩れていたので、戻り値だけでは検出できない。
  現在は配置後に`GetWindowRect`で測り直し、`Arranged N of M`のNに実測一致数を入れている。
- **ai-dotfilesからscript本体を削除した。** ai-dotfiles側のSkillは指示書だけになり、
  このfileを呼ぶ薄い接続になった。`~/.claude/skills/align-terminals/`にcopyは無い。

## 壊してはいけない前提

- **`~/Projects/Others/align-terminals/align_terminals.pyw`というpathとfile名。**
  ai-dotfilesの`skills/align-terminals/SKILL.md`がこの文字列を持っている。
  移動やrenameをする場合は、ai-dotfiles側のcanonical sourceを同時に直し、
  generate、check、install、full checkまで通す必要がある。runtime側の
  `~/.claude/skills/`を直接編集しないこと。
- **two-passを1周に戻さない。** 混在DPI環境で必ず壊れる。理由は`DPI-verification.md`。
- **収束するまで繰り返すretry loopにもしない。** 2周目で確定するので3周目以降は無意味。
- **`SetProcessDpiAwarenessContext`でDPI-awareにしない。** 再スケールはTerminal側が
  境界越えに反応して行うので防げず、`OFFSET`と`MIN_WIDTH`のDPI換算という別問題を抱える。

## 変更したときの検証手順

単に実行して見た目を確認するだけでは不十分。**混在DPI状態から始めないとbugは再現しない。**
片方のmonitorにしかwindowが無い状態で試すと、壊れた版でも正しく見える。

```text
py -3 tools/snapshot_rects.py before.json
（windowを何枚かsecondary monitorへ移す）
py -3 tools/snapshot_rects.py before.json
py -3 align_terminals.pyw
py -3 tools/dpi_probe.py
```

`dpi_probe.py`の出力で、全windowが同じ`w`と`h`になっていることを確認する。
元の配置へ戻すときは`py -3 tools/restore_rects.py before.json`を2回実行する
（復元も逆向きのDPI境界を跨ぐため1回では戻りきらない）。

summary行の`N of M`は`GetWindowRect`の実測なので、これが`5 of 5`のように揃っていれば
それ自体が証拠になる。`3 of 5`のような出力が出たらDPI関連を疑う。

## やりかけ・次にやること

- **taskbar shortcutをまだ作っていない。** ユーザーが置く予定。
  shortcutのtargetは`align_terminals.pyw`を直接指す想定。
- **double-click起動ではsummaryが見えない。** `pythonw.exe`にはconsoleが無く
  `sys.stdout`が`None`になるため`print()`がno-opになる。taskbar用途では
  windowが並べば目的は果たされるので実害は無いが、診断を残したくなったら
  log fileへの出力を足すのが素直。なおこれは`pythonw.exe`の仕様からの推定で、
  double-click起動での実測はしていない。
- **remoteが無い。** localのcommitだけがある状態。公開する予定ができたら追加する。
- **`MIN_WIDTH` 640のfloorに当たるとbandが280pxより狭くなる。** 7枚で
  offset 213pxまで縮むことを実測済み。意図した挙動だが、常用枚数が多いなら
  定数の見直し余地がある。
- **taskbar以外のhostへの配布は考えていない。** macOSでは動かない
  （Win32 API依存）。ai-dotfiles側のSkillは、toolが見つからなければ
  推測せず停止するようになっている。
