# align-terminals

開いているWindows Terminalのwindowを、primary monitorのwork areaへ隙間なく敷き詰める
単体tool。並行して動かしているagent sessionを一望するために作った。もう一度実行すると
並べる前の位置へ戻す。

Windows専用。標準libraryの`ctypes`だけを使い、外部依存を持たない。

## 使い方

```console
py -3 align_terminals.pyw --arrange    # 常に整列
py -3 align_terminals.pyw --restore    # 常に復元
py -3 align_terminals.pyw              # toggle（taskbarのshortcut用）
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

`.pyw`なのでdouble-clickでは`pythonw.exe`が使われ、consoleが無いためsummaryは見えない。
taskbarから使うぶんには実害が無い。出力を読みたいときは上のようにconsoleから起動する。

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

`align_terminals.ico`が付属する。shortcutのtargetを次の形にして、iconにこのfileを指定する。

```text
C:\WINDOWS\pyw.exe -3 "<project>\align_terminals.pyw"
```

**taskbarへのpinは手作業。** Windows 11では`taskbarpin`のshell verbが削除されているので
scriptから留められない。Startで名前を入力し、右clickして「タスクバーにピン留めする」を選ぶ。

iconを描き直したいときは`py -3 tools/make_icon.py`。標準libraryだけでPNG/DIBを描いて
`.ico`へ詰める。

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

変更する前に[`AGENTS.md`](AGENTS.md)の「守ること」を読むこと。上の罠は一度直しても、
知らずに書き戻すと簡単に再発する。

## Tools

| file | 用途 |
|---|---|
| `tools/layout_preview.py` | 配置の算術を実機なしで確認する |
| `tools/zorder_probe.py` | top-level windowのz-orderを前面から順に実測する（read-only） |
| `tools/make_icon.py` | `align_terminals.ico`を生成する |
| `tools/dpi_probe.py` | monitor構成とDPIを表示する |
| `tools/snapshot_rects.py`, `tools/restore_rects.py` | 検証中にwindow座標を保存・復元する |
