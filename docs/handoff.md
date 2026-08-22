# handoff: align-terminals

2026-08-22作成。ai-dotfilesからこのprojectを切り出したsessionからの引き継ぎ。

## このprojectは何か

Windows Terminalのwindowを、primary monitor上で左から右へcascade配置する単体tool。
並行して動かしているagent sessionを一望するために使う。

5枚までは全高で1段。6枚目からは右の列から順に上下へ割って2段にし、下段は分割した列の
左から埋める。10枚を超えると列数を増やして2段を保つ。もう一度実行すると直前の位置へ戻る。

起動経路は2つある。**どちらも同じ`align_terminals.pyw`を使う。**

1. **taskbarのshortcut** — clickで即実行。console windowを出さないため拡張子が`.pyw`。
   （shortcut自体はまだ作っていない。ユーザーが後で置く予定）
2. **AI経由** — ai-dotfilesの`align-terminals` Skillがこのfileを呼ぶ。

## file構成

| path | 役割 |
|---|---|
| `align_terminals.pyw` | 本体。標準libraryのctypesだけ。外部依存なし |
| `DPI-verification.md` | **先に読むこと。** 実機検証の記録と、two-passを消してはいけない理由 |
| `tools/layout_preview.py` | `layout()`の割り当てをtext gridで出力。実機なしで算術だけ確認する |
| `tools/dpi_probe.py` | DPI-awareな観測。monitor構成、per-monitor DPI、各windowの実測rect |
| `tools/snapshot_rects.py` | 実行前のwindow座標をJSONへ保存 |
| `tools/restore_rects.py` | snapshotから復元。検証の開始状態を作り直すのに使う |

git repositoryにしてある（2026-08-22、branchは`main`、remoteは未設定）。
`.gitignore`はroot直下の`*.json`を除外するので、検証で作るsnapshotは追跡されない。

復元用のstateは`%LOCALAPPDATA%\align-terminals\last_layout.json`に置く。repositoryには
書かない。`arranged`（自分が並べた直後の実測）と`previous`（並べる前の実測）を持ち、
前者と現在の実測が完全一致したときだけ後者へ戻す。

## 2段配置と復元を入れたsession（2026-08-22）

- **6枚目から2段になるようにした。** 割り当ては純関数`layout()`に閉じている。
  列は`max(5, (n+1)//2)`、分割するのは右から`n - 列数`列。下段は分割した列の左から埋める。
  6〜10枚では列数が5に固定されるので、band幅が枚数分だけ狭まる問題は起きなくなった。
- **引数なしのtoggleで元の位置へ戻るようにした。** 並べた直後の実測をsnapshotへ残し、
  次の実行で現在の実測と完全一致したら復元する。手でwindowを動かしたあとに実行すると
  一致しないので、通常の整列になる。意図せざる復元は起きない。
  最小化されていたwindowは、復元後にもう一度最小化する。
- **復元も2周適用にした。** 逆向きにDPI境界を跨ぐので、整列と同じ理由で1周では戻りきらない。
- **検証を目標rect単位にした。** windowごとに高さが違うため、以前の「全windowが同じ`w`と`h`」
  という判定は使えない。`placed_as_requested`相当の照合がDPI回帰を検出する唯一の砦になった。
- **実機で9枚まで確認した。** 混在DPIから`Arranged 9 of 9`、`Restored 9 of 9`。
  整列後に1枚だけ手で動かしてから再実行すると復元ではなく整列になることも確認した。
  実測値は`DPI-verification.md`にある。

## それ以前のsessionでやったこと

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
- **番号と枠の対応を変えない。** 上段は左から1枚目、下段は分割した列の左から順。
  userはこの並びで自分のsessionを覚えるので、対応が変わると実質的な破壊になる。
- **復元を「一致したときだけ」から緩めない。** 手で動かしたwindowを勝手に戻すのが
  一番困る失敗の形。判定は実測rectの完全一致で行う。

## 変更したときの検証手順

単に実行して見た目を確認するだけでは不十分。**混在DPI状態から始めないとbugは再現しない。**
片方のmonitorにしかwindowが無い状態で試すと、壊れた版でも正しく見える。

```text
py -3 tools/layout_preview.py            # 算術だけ先に見る。実機は不要
py -3 tools/snapshot_rects.py before.json
（windowを何枚かsecondary monitorへ移す）
py -3 tools/snapshot_rects.py before.json
py -3 align_terminals.pyw                # 整列
py -3 tools/dpi_probe.py
py -3 align_terminals.pyw                # もう一度実行すると復元
py -3 tools/dpi_probe.py
```

**判定条件は「全windowが同じ`w`と`h`」ではない。** 2段配置ではwindowごとに目標が違う。
summary行の`N of M`が`7 of 7`のように揃っていることを見る。これは`GetWindowRect`の実測
なので、それ自体が証拠になる。`3 of 7`のような出力が出たらDPI関連を疑う。
`dpi_probe.py`の出力は、`layout_preview.py`が示した割り当てと突き合わせて読む。

`layout_preview.py`が確認できるのは割り当ての算術だけで、DPIの挙動は実機でしか出ない。
両方を通さないと検証にならない。

復元は本体のtoggleで足りる。`tools/restore_rects.py`は、検証の開始状態
（混在DPI配置）を何度も作り直したいときに使う。こちらは2回実行する。

## やりかけ・次にやること

- **taskbar shortcutをまだ作っていない。** ユーザーが置く予定。
  shortcutのtargetは`align_terminals.pyw`を直接指す想定。1つのshortcutが整列と復元の
  両方を兼ねる（2回目のclickで戻る）ので、復元用に別のshortcutを置く必要はない。
- **ai-dotfiles側のSKILL.mdが古い挙動を書いている。** `skills/align-terminals/SKILL.md`は
  「呼べば整列する」前提で書かれている。今はSkill経由で1回、taskbarから1回と続けて呼ぶと
  2回目が復元になる。canonical sourceへtoggleの説明を足す必要があるが、このsessionでは
  別repositoryなので触っていない。
- **最小化されていたwindowの経路は実機未確認。** `iconic`の記録と復元後の再最小化は、
  検証中に最小化されたwindowが無かったため一度も通っていない。論理上は、最小化中のwindowは
  rectが`-32000`になって`arranged`と一致しないので、再最小化されるのは整列時に自分が
  復帰させたwindowだけになる。
- **double-click起動ではsummaryが見えない。** `pythonw.exe`にはconsoleが無く
  `sys.stdout`が`None`になるため`print()`がno-opになる。taskbar用途では
  windowが並べば目的は果たされるので実害は無いが、診断を残したくなったら
  log fileへの出力を足すのが素直。なおこれは`pythonw.exe`の仕様からの推定で、
  double-click起動での実測はしていない。
- **remoteが無い。** localのcommitだけがある状態。公開する予定ができたら追加する。
- **`MIN_WIDTH` 640のfloorに当たるとbandが狭くなる。** 6〜10枚では列数が5に固定される
  ので、この範囲では起きなくなった。11枚以上、または作業領域が狭い環境では依然として
  起きる。1366x728で5列にすると offset 181px まで縮むことを`layout_preview.py`で確認済み。
- **作業領域が縦に短いと、半分の高さがTerminalの最小window高に当たる可能性がある。**
  768px級の環境で半分が約384px。当たると`N of M`が欠ける形で出る。未確認。
- **復元後、物理pxで1pxずれることがある。** 実測で 183→184、-1497→-1496。
  DPI非対応の座標系では奇数の物理px座標を表現できないための丸めで、bugではない。
  scriptの座標系では完全一致（だから`Restored N of N`）。詳細は`DPI-verification.md`。
- **taskbar以外のhostへの配布は考えていない。** macOSでは動かない
  （Win32 API依存）。ai-dotfiles側のSkillは、toolが見つからなければ
  推測せず停止するようになっている。
