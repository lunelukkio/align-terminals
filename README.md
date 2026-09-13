# align-terminals

Tiles open Windows Terminal windows across the primary monitor's work area with
no gaps. Built to see every running agent session at a glance. Run it again to
put the windows back where they were.

Windows only. The production implementation is in Rust and produces two exe
files. The original Python version (`align_terminals.pyw`) is kept as the
verification oracle.

## Usage

```console
align-terminals.exe --arrange    # always arrange
align-terminals.exe --restore    # always restore
align-terminals.exe              # toggle
align-terminalsw.exe             # same, windowed build (no console) for taskbar shortcuts
```

With no arguments it toggles: if no window has moved since the last arrange, it
restores; otherwise it arranges. **It never restores on its own after you move
a window by hand.**

`--restore` reports and does nothing if the current layout doesn't match the
last arranged layout. It never falls back to arranging — silently rearranging
when the user asked to restore would be the worst failure mode.

Each run prints a one-line summary. The numbers are measured after placement,
not an echo of the requested values.

```text
Arranged 7 of 7 Windows Terminal windows: 4 column(s), 2 row(s), width 473px/480px,
offset 480px, height 540px/1080px, measured after placement. Run again to put them back.
```

There are two exes for the same reason `python.exe` / `pythonw.exe` are
separate. `align-terminals.exe` is the console build; its stdout can be
captured from any shell, so scripts call this one. `align-terminalsw.exe` is
the windowed build; no console flashes even when launched from a shortcut. As
a tradeoff, a plain PowerShell invocation neither captures nor waits for it,
so scripts must not call it.

## Build

```console
cargo build --release
powershell -File tools/deploy.ps1   # builds and refreshes the two exes at the repo root
```

Dependencies are just `windows-sys` and `serde`. The shortcut and the Skill
point at the repo-root exes, so a plain build alone has no effect until
`tools/deploy.ps1` copies them over.

## Layout

Each row holds at most 5 windows. A 6th window starts a 2nd row, an 11th
starts a 3rd. Width is the work-area width divided by the column count, never
narrower than a quarter. Up to 4 columns tile exactly; 5 columns overlap
evenly while keeping that width. Any remainder that doesn't divide evenly into
rows becomes a full-height column on the left.

| count | rows | cols | width | layout |
|---|---|---|---|---|
| 1 | — | — | — | left in place, just brought to front |
| 2 | 1 | 2 | 1/2 | 2 side by side, full height |
| 3 | 1 | 3 | 1/3 | 3 side by side, full height |
| 4 | 1 | 4 | 1/4 | 4 side by side, full height |
| 5 | 1 | 5 | 1/4 | 5 side by side, full height, evenly overlapping |
| 6 | 2 | 3 | 1/3 | 3 on top, 3 on bottom |
| 7 | 2 | 4 | 1/4 | 1 full-height column on the left + 3 columns × 2 rows |
| 8 | 2 | 4 | 1/4 | 4 columns × 2 rows |
| 9 | 2 | 5 | 1/4 | 1 full-height column on the left + 4 columns × 2 rows, overlapping |
| 10 | 2 | 5 | 1/4 | 5 columns × 2 rows, overlapping |

Placement order follows reading order: the full-height column on the left
first, then the top row left to right, then the next row. Windows further
right end up more in front, so an overlapped window still shows the left edge
of the one behind it. Re-arranging an already-arranged layout keeps each
window in the same slot.

You can check the assignment without a real machine:

```console
py -3 tools/layout_preview.py 16 1920 1040
```

## Using it from the taskbar

Point the shortcut's target at:

```text
<project>\align-terminalsw.exe
```

The icon is embedded in the exe, so the shortcut can point at the exe itself.

**Pinning to the taskbar is manual.** Windows 11 removed the `taskbarpin`
shell verb, so it can't be pinned from a script. Type the name in Start,
right-click, and choose "Pin to taskbar".

To redraw the icon, run `py -3 tools/make_icon.py`. It draws PNG/DIB with only
the standard library and packs it into `.ico`. After redrawing, re-embed it
into the exes with `tools/deploy.ps1`.

## Where state is stored

Restore coordinates live in
`%LOCALAPPDATA%\align-terminals\last_layout.json`, not in the repository. It
holds both the measurement taken right after arranging and the one taken
before arranging, and only restores to the latter when the former matches the
current measurement exactly.

## Why the implementation looks like this

Window z-order and DPI have a few traps that a straightforward implementation
always hits. The verification record is in
[`DPI-verification.md`](DPI-verification.md). The highlights:

- **The same geometry is applied twice.** A window that crosses a monitor's
  DPI boundary rescales itself in response to `WM_DPICHANGED`, overwriting the
  size you set. Dropping this to a single pass breaks in any mixed-DPI setup.
- **Bringing a window to front is done separately from geometry, via one
  round trip through `HWND_TOPMOST` → `HWND_NOTOPMOST`.** `HWND_TOP` clamps
  the target just below the current foreground window when the calling
  process doesn't own the foreground window — and `SetWindowPos` still
  reports success, so the failure is silent.
- **`GetWindowRect` includes the invisible resize border.** Placing windows
  edge-to-edge using that rect leaves a visible gap of two borders. Each
  window's border is measured and the requested rect is expanded accordingly.
- **On a DPI-unaware process, coordinates outside the primary monitor are
  interpreted at the neighboring monitor's scale.** Requesting `left = -7`
  lands at `-5`. So edges that spill onto another monitor are never expanded.
- **DPI awareness is pinned to unaware, explicitly, in the manifest.**
  Virtualized coordinates are the basis for every measurement here; making the
  process system-DPI-aware switches it to physical coordinates and throws
  everything off. This was hit for real on the first Rust build.

Read the "Must keep" section of [`AGENTS.md`](AGENTS.md) before changing
anything — these traps are easy to reintroduce once fixed if you don't know
they're there.

## Python oracle

`align_terminals.pyw` is off the production path but not deleted. It serves as
the behavioral reference.

- `tools/gen_layout_fixture.py` records 245 cases from `layout()`'s output, and
  `cargo test` asserts an exact match against the Rust version (the only
  differential check that runs without real hardware).
- When Rust's behavior is in doubt, run both implementations under the same
  conditions and diff stdout and probe output. A mismatch is treated as a bug
  in the Rust side.

The CLI and summary strings match byte-for-byte between the two
implementations (only the program name in usage text differs). They also
share the same snapshot file, so either one can restore a layout the other
arranged.

## Tools

| file | purpose |
|---|---|
| `tools/deploy.ps1` | release-builds and refreshes the two exes at the repo root |
| `tools/gen_layout_fixture.py` | regenerates the `cargo test` fixture from the Python oracle |
| `tools/drawn_rects.py` | measures drawn rects and seams (read-only); gaps don't show in the summary |
| `tools/layout_preview.py` | checks the placement arithmetic without real hardware |
| `tools/zorder_probe.py` | measures top-level window z-order, front to back (read-only) |
| `tools/make_icon.py` | generates `align_terminals.ico` |
| `tools/dpi_probe.py` | prints monitor layout and DPI |
| `tools/snapshot_rects.py`, `tools/restore_rects.py` | save/restore window coordinates during verification |

---

*日本語版は下にあります。*

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
