# align-terminals

開いているWindows Terminalのwindowを、primary monitorのwork areaへ隙間なく敷き詰める
単体tool。並行して動かしているagent sessionを一望するために作った。もう一度実行すると
並べる前の位置へ戻す。

Windows専用。本番はRust実装で、exeが2本できる。Pythonで書かれた初代
（`align_terminals.pyw`）は検証の正解表（oracle）として残っている。

## 使い方

```console
align-terminals.exe --arrange    # 常に整列
align-terminals.exe --restore    # 常に復元
align-terminals.exe              # toggle
align-terminalsw.exe             # 同上。console窓を出さない版（taskbarのshortcut用）
```

引数なしはtoggleとして動く。前回並べた位置からwindowが1枚も動いていなければ復元、
動いていれば整列。**手で動かしたあとに勝手に復元することはない。**

`--restore`は、前回の整列位置と一致しないときは何も動かさずにその旨を報告する。
整列へfallbackしない。「戻して」と頼まれて並べ替えるのが一番困る失敗だから。

実行するとsummaryを1行出す。数値は要求値の復唱ではなく、配置後に測り直した実測。

```text
Arranged 7 of 7 Windows Terminal windows: 4 column(s), 2 row(s), width 473px/480px,
offset 480px, height 540px/1080px, measured after placement. Run again to put them back.
```

exeがpython.exe / pythonw.exeと同じ理由で2本ある。`align-terminals.exe`はconsole版で、
どのshellからでもstdoutを捕捉できる。scriptから呼ぶのはこちら。`align-terminalsw.exe`は
windowed版で、shortcutから起動してもconsoleが一瞬も出ない。かわりにPowerShellは素の
呼び出しでは出力を捕捉も待機もしないので、scriptからは呼ばない。

## Build

```console
cargo build --release
powershell -File tools/deploy.ps1   # buildしてrepo rootの2つのexeを更新する
```

依存は`windows-sys`と`serde`だけ。shortcutとSkillはrepo rootのexeを指しているので、
buildしただけでは反映されない。`tools/deploy.ps1`がcopyまで行う。

## 配置

1段は最大5枚。6枚目から2段、11枚目から3段になる。幅は列数で割るが、4分の1より狭くは
しない。4列まではぴったり並び、5列になると幅を保ったまま均等に重なる。段数で割り切れない
余りは、左端の全高列になる。

| 枚数 | 段 | 列 | 幅 | 構成 |
|---|---|---|---|---|
| 1 | — | — | — | 動かさず前面へ出すだけ |
| 2 | 1 | 2 | 1/2 | 横に2枚、全高 |
| 3 | 1 | 3 | 1/3 | 横に3枚、全高 |
| 4 | 1 | 4 | 1/4 | 横に4枚、全高 |
| 5 | 1 | 5 | 1/4 | 横に5枚、全高、均等に重なる |
| 6 | 2 | 3 | 1/3 | 上3・下3 |
| 7 | 2 | 4 | 1/4 | 左に全高1枚＋3列×2段 |
| 8 | 2 | 4 | 1/4 | 4列×2段 |
| 9 | 2 | 5 | 1/4 | 左に全高1枚＋4列×2段、重なる |
| 10 | 2 | 5 | 1/4 | 5列×2段、重なる |

配置順は読む順。左端の全高列から始まり、上段を左から右、次に下段を左から右。右にある
windowほど前面になるので、重なっても後ろのwindowは左端の帯を見せる。整列済みの状態で
もう一度整列しても、各windowは同じ枠に留まる。

実機なしで割り当てを確認できる。

```console
py -3 tools/layout_preview.py 16 1920 1040
```

## taskbarから使う

shortcutのtargetを次の形にする。iconはexeに埋め込み済みなのでexe自身を指せばよい。

```text
<project>\align-terminalsw.exe
```

**taskbarへのpinは手作業。** Windows 11では`taskbarpin`のshell verbが削除されているので
scriptから留められない。Startで名前を入力し、右clickして「タスクバーにピン留めする」を選ぶ。

iconを描き直したいときは`py -3 tools/make_icon.py`。標準libraryだけでPNG/DIBを描いて
`.ico`へ詰める。描き直したら`tools/deploy.ps1`でexeへ埋め込み直す。

## 状態の保存先

復元用の座標は`%LOCALAPPDATA%\align-terminals\last_layout.json`に置く。repositoryには
書かない。並べた直後の実測と並べる前の実測を持ち、前者と現在の実測が完全一致したときだけ
後者へ戻す。

## この実装がこの形をしている理由

Windowのz-orderとDPIには、素直に書くと必ず踏む罠がいくつかある。実測の記録は
[`DPI-verification.md`](DPI-verification.md)にある。要点だけ挙げると:

- **同じgeometryを2回要求する。** monitorのDPI境界を跨いだwindowは`WM_DPICHANGED`で
  自分を再スケールし、指定したサイズを上書きする。1回に減らすと混在DPI環境で必ず壊れる。
- **前面化はgeometryと分けて`HWND_TOPMOST`→`HWND_NOTOPMOST`の一往復で行う。**
  `HWND_TOP`は、呼び出し側processがforeground windowを所有していないと対象をその下へ
  clampする。しかも`SetWindowPos`は成功を返すので気づけない。
- **`GetWindowRect`は描画されないリサイズ枠を含む。** その座標で隣接させると見た目には
  枠2つ分の隙間が空く。windowごとに枠を実測して要求rectを広げている。
- **DPI-unawareなprocessでは、primary monitorの外の座標が隣のmonitorの倍率で読まれる。**
  `left = -7`を要求すると`-5`に着地する。だから別monitorへはみ出す辺は広げない。

- **DPI awarenessはmanifestで明示的にunawareへ固定してある。** virtualized座標こそが
  実測の基盤で、system-DPI-awareにするとphysical座標になり全部ずれる。Rust移植の
  初回buildで実際に踏んだ。

変更する前に[`AGENTS.md`](AGENTS.md)の「守ること」を読むこと。上の罠は一度直しても、
知らずに書き戻すと簡単に再発する。

## Python oracle

`align_terminals.pyw`は本番経路から外れたが削除しない。挙動の正解表として使う。

- `tools/gen_layout_fixture.py`が`layout()`の出力245 caseを記録し、`cargo test`が
  Rust版との完全一致を検証する（実機なしで回る唯一のdifferential）。
- 実機の挙動を疑うときは、同じ状況で両実装を走らせてstdoutとprobe出力をdiffする。
  一致しなければRust側の誤りとして直す。

CLIとsummary文字列は両実装でbyte一致（usageのprogram名だけ違う）。snapshotも同じ
fileを共有し、片方が並べたものをもう片方が復元できる。

## Tools

| file | 用途 |
|---|---|
| `tools/deploy.ps1` | release buildしてrepo rootの2つのexeを更新する |
| `tools/gen_layout_fixture.py` | Python oracleから`cargo test`用のfixtureを再生成する |
| `tools/drawn_rects.py` | 描画rectと継ぎ目を実測する（read-only）。隙間はsummaryに出ない |
| `tools/layout_preview.py` | 配置の算術を実機なしで確認する |
| `tools/zorder_probe.py` | top-level windowのz-orderを前面から順に実測する（read-only） |
| `tools/make_icon.py` | `align_terminals.ico`を生成する |
| `tools/dpi_probe.py` | monitor構成とDPIを表示する |
| `tools/snapshot_rects.py`, `tools/restore_rects.py` | 検証中にwindow座標を保存・復元する |
