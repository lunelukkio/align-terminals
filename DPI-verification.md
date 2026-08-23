# align-terminals 実機検証記録 (2026-08-22)

`align_terminals.pyw` が現在の形になった理由を残す。とくに **最終 geometry を2回要求する
配置**は、知らずに1回へ戻すと混在 DPI 環境で必ず壊れるので、消さないこと。
下の節は時系列で並んでいる。関数名や周回数は後の節で変わっているので、
現在の実装は最後の節を基準に読むこと。

## 検証環境

- Windows 11 Pro 10.0.26200
- PRIMARY monitor: 3840x2160 @ 192 DPI (200%)、work area = monitor 全体（タスクバーは auto-hide）
- secondary monitor: (-2560,0)-(0,1440) @ 144 DPI (150%)
- interpreter: `py.exe -3` (Python 3.13.5)。virtualized な 1920x1080 を見る。
  **注記 (2026-08-23): 当初ここに「system-DPI-aware なので」と書いたが、それは誤り。**
  virtualized 座標を見るのは **DPI-unaware** の挙動で、system-DPI-aware はその逆
  （physical を見る）。観測値は正しく、awareness の名前だけが間違っていた。
  この誤記を信じて Rust 移植の manifest を `dpiAware=true` にしたら座標空間が
  3840x2160 になった。詳細は下の「Rust 移植」の節
- 対象 window: 5枚。うち3枚は実行前 secondary 側

## 見つかった不具合と修正

### 症状

secondary (144 DPI) から primary (192 DPI) へ移動した window だけ、指定したサイズにならない。

| window | 期待 (physical) | 1周のみの実測 |
|---|---|---|
| secondary から来た3枚 | 1600x2160 | **2133x2190** |
| もともと primary の2枚 | 1600x2160 | 1600x2160 |

`2133 / 1600 = 192 / 144 = 4/3` ちょうど。X 座標と z-order は正しいまま。

### 原因

`SetWindowPos` で window が monitor の DPI 境界を跨ぐと、移動が着地した時点で Windows が
`WM_DPICHANGED` を送る。Windows Terminal は per-monitor DPI aware なので、
destination / source の DPI 比で自分を再スケールする。これは `SetWindowPos` が
成功を返した**後**に起こるため、指定したサイズが上書きされる。位置と z-order は上書きされない。

### 修正

同じ geometry を2周適用する。1周目の後は全 window が primary 上にいるので、
2周目は DPI 境界を跨がずサイズが定着する。

**1周で十分だと思って戻さないこと。逆に、収束するまで繰り返す retry loop にもしないこと。**
2周目で確定するので、3周目以降にやることは無い。

### 検証方法

実行前の座標を JSON へ保存し、mixed-monitor 状態へ復元してから2回試した。
2回とも5枚すべてが `1600x2160` / `x = 0, 560, 1120, 1680, 2240` に一致。
`sleep` は不要だった。つまり `WM_DPICHANGED` は `SetWindowPos` 内で同期的に処理される。

7枚（`MIN_WIDTH` 640 の floor に当たり offset 213 へ縮小）でも `7 of 7` で一致した。

## 2段配置と復元での再検証 (2026-08-22)

2段配置と復元 toggle を入れたあと、同じ環境で測り直した。

- 9枚（うち2枚は実行前 secondary 側）で `Arranged 9 of 9`。physical で
  x = 0, 560, 1120, 1680, 2240 / 幅 1600、1列目のみ高さ 2160、2〜5列目は 1080 ずつ上下。
  z-order は下から 1列目 → 上段左から右 → 下段左から右。`layout_preview.py` の割り当てと一致。
- 3枚での `Arranged 3 of 3` と `Restored 3 of 3` も通っている。
- **復元も2周適用が要る。** 戻すときは逆向きに DPI 境界を跨ぐ。1周で足りるように見えても
  戻さないこと。理由は上と同じ。
- 整列後に window を1枚だけ手で動かしてから再実行すると、復元ではなく整列になる。
  復元判定を実測 rect の完全一致にしてあるため。意図せざる復元は起きない。

### 復元後に physical で 1px ずれることがある

実測で 183 → 184、-1497 → -1496。**これは DPI-unaware な座標系の丸めであって bug ではない。**
200% monitor 上では奇数の physical 座標を unaware 座標で表現できない（183 / 2 = 91.5 → 92 → 184）。
script が扱う座標系では完全一致しており、だから `Restored N of N` になる。

**ただし復元先が負の x を持つ場合は、script の座標系でも一致しない。** primary monitor の
外の座標は隣の monitor の倍率で解釈されるため（下の「負の座標は隣のmonitorの倍率で
解釈される」を参照）。`-4` が `-3` に着地して `Restored 6 of 7` になる例を実測している。
直そうとすると DPI-aware 化の話になり、それは下の理由で採らない。

## 整列した window が browser の後ろへ沈む不具合 (2026-08-22)

### 症状

user 報告は「何回か起動させると、だんだん後ろに移っていく」。
`tools/zorder_probe.py` で実測したところ、**2回目以降で安定して再現**した。

再現条件は「chrome を前面にした状態で、foreground window を所有していない process から
`--arrange` を起動する」。taskbar shortcut から起動したときの条件そのもの。

| run | terminal の z | chrome の z |
|---|---|---|
| 1 | 40, 42, 44 | 47（3枚とも前） |
| 2〜5 | **40**, 46, 47 | **43**（最前面の1枚だけが前、残り2枚が後ろ） |

### 原因

`SetWindowPos(hwnd, HWND_TOP, ...)` は、呼び出し側 process が foreground window を
所有していないとき、対象を**現在の foreground window のすぐ下へ clamp** する。
失敗にはならず TRUE を返すので、呼び出し側からは成功に見える。

そのため配置 pass の2周目にあった持ち上げは chrome を越えられていなかった。
最後の `SetForegroundWindow(ordered[-1])` が成功する1枚だけが chrome の上に出て、
残りは chrome の下に取り残される。これが「1枚だけ前、あとは後ろ」の内訳。

### 修正

持ち上げを geometry から切り離し、z-order 専用の `raise_to_front` を新設した。
window ごとに `HWND_TOPMOST` → `HWND_NOTOPMOST` を一往復させる。topmost band への
出入りは上の clamp を受けないので、通常 band の先頭へ確実に入る。左から順に往復させると
右端が最前面になり、配置順と一致する。

配置 pass（当時 `apply_twice`、現在 `place()`）は全周とも `SWP_NOZORDER` になり、
geometry 専用になった。副次的に、復元経路が z-order を触らないことが分岐ではなく
構造で保証される。

**`raise_to_front` は `SWP_NOMOVE | SWP_NOSIZE` で呼ぶこと。** geometry を伴わない
`SetWindowPos` は `WM_DPICHANGED` を誘発しないので、上の two-pass 配置と干渉しない。
ここに geometry を混ぜると混在 DPI の話がぶり返す。

### 検証

- **前面化**: chrome を前面にしてから `--arrange`、を5回連続。5回とも terminal 3枚が
  z40 / 42 / 44、chrome は z47。右端が最前面。1回目から5回目まで変化なし。
- **topmost に居残らない**: 実行後の probe で terminal に `WS_EX_TOPMOST` は立っていない。
- **常時 topmost の app は上に残る**: `aqua voice.exe`（TOPMOST, z29）は terminal より
  前のまま。通常 band の先頭までしか上げないので、これは意図どおり。
- **復元は z-order を触らない**: chrome を前面にしてから `--restore`。
  `Restored 3 of 3` の後も chrome が z39 で前面、terminal は z43 / 45 / 47 のまま。
- **引数なし toggle**: 整列 → 復元 → 整列が期待どおり。
- **混在 DPI の回帰確認**: 1枚を secondary (144 DPI) へ 800x700 で置くと 600x525
  （= 0.75 = 144/192）へ再スケールされる状態を作ってから `--arrange`。`Arranged 3 of 3`。
  2周適用は壊れていない。**この確認はこの時点の code に対するもので、下の配置規則
  作り直しと隙間埋めより前。現在の code に対する混在 DPI 検証は最後の節にある。**

## 配置規則の作り直しと隙間埋め (2026-08-22)

### 新しい配置規則

userの指定で、cascadeから敷き詰めへ変えた。規則は3行に収まる。

```
段数 rows    = ceil(count / MAX_PER_ROW)        MAX_PER_ROW = 5
縦長 tall    = count % rows                     左端に置く全高列
列数 columns = tall + count // rows
幅   width   = 作業領域幅 / min(columns, MAX_TILED_COLUMNS)   MAX_TILED_COLUMNS = 4
間隔 offset  = (作業領域幅 - width) / (columns - 1)
```

順序は読む順。全高列 → 上段を左から右 → 次の段。`layout_preview.py`で1〜16枚を確認した。

| n | 段 | 列 | 幅 | 重なり | 構成 |
|---|---|---|---|---|---|
| 1 | — | — | — | — | 動かさず前面へ出すだけ |
| 2 | 1 | 2 | 960 | 0 | 2並び |
| 3 | 1 | 3 | 640 | 0 | 3並び |
| 4 | 1 | 4 | 480 | 0 | 4並び |
| 5 | 1 | 5 | 480 | 120 | 5並び、均等に重なる |
| 6 | 2 | 3 | 640 | 0 | 上3・下3 |
| 7 | 2 | 4 | 480 | 0 | 縦長1＋3列×2段 |
| 8 | 2 | 4 | 480 | 0 | 4列×2段 |
| 9 | 2 | 5 | 480 | 120 | 縦長1＋4列×2段 |
| 10 | 2 | 5 | 480 | 120 | 5列×2段 |

**`ordered`のsort keyを`(top, left)`にしたので、`count >= 7`の席替え不具合も同時に消えた。**
`layout()`のemission順とsort順が一致するようになったため。7枚で3回連続`--arrange`し、
hwnd → rectの対応が完全に不変であることを実測した。

`MIN_WIDTH` 640と`OFFSET` 280は廃止した。1/4幅の下限がその役目を兼ねる。

### 隙間の原因は不可視のリサイズ枠

user報告は「それぞれのウィンドウの間に隙間が空いている」。

`GetWindowRect`は描画されないリサイズ枠を含む。実測でこの環境の枠は
**scriptの座標系でL7 / T0 / R6 / B7**（DWMの可視枠基準では物理11px）。
そのため`GetWindowRect`の座標で隣接させると、隣り合う2枚で枠2つ分の隙間が見える。

修正は`outset()`。windowごとに枠を実測し、要求rectをその分だけ外へ広げる。
枠は`GetClientRect` + `ClientToScreen`から求める。**この2つはscriptと同じ座標系を返すので
倍率換算が要らない。** `DwmGetWindowAttribute`は物理座標を返すため換算が必要になり、
DPI-unawareのまま扱うには向かない。

### 負の座標は隣のmonitorの倍率で解釈される

左端の列を広げようとして見つかった。**DPI-unawareなprocessでは、primary monitorの外の
座標が隣のmonitorの倍率で読まれる。** 実測（secondaryは144 DPI、primaryは192 DPI）:

| 要求した left | 着地した left | 比 |
|---|---|---|
| -1 | -1 | -0.75 → -1 |
| -7 | **-5** | -5.25 → -5 |
| -20 | **-15** | -15.0 |

いずれも `left × 144/192`。右方向（x > 1920）はmonitorが無いので素通しし、要求どおりに着地する。

そこで`outset()`は、広げる先の点が別のmonitor上になる辺だけ広げない。desktopの外へ
はみ出す辺は広げてよい。結果として左端だけ枠の分（7px）内側から始まり、右端と下端は
ぴったりになる。`placed`の判定は`outset()`が返す到達可能なrectと比べる。広げられなかった
辺の分を目標から差し引かないと、この環境では常に`N-1 of N`になって本物の失敗を隠す。

**同じ理由で、復元先のrectが負のxを持つときは完全一致で戻せない。** `previous`に`-4`が
入っていたcaseで`-3`に着地し`Restored 6 of 7`になった。復元経路の性質であって、
隙間埋めとは独立。「復元後に物理pxで1pxずれる」の節は、負の座標ではscript自身の
座標系でも1pxずれることを補足しておく。

### DPI再スケール直後は枠の値が一時的にずれる

隙間埋めを入れた直後の混在DPI検証で`Arranged 2 of 3`になって見つかった。
secondaryから来たwindowだけ描画幅が641px（目標640px）になる。

段階を追って実測した結果:

| 段階 | frame | 枠 L/T/R/B |
|---|---|---|
| secondaryに置いた直後 | (-1000,100,600,525) | 8/0/7/7 |
| 1周目（境界を跨ぐ）の直後 | (1280,0,854,1095) | **7/0/7/7** |
| 2周目（この枠で計算）の直後 | (1273,0,654,1087) | 7/0/6/7 |

**枠はwindowのサイズによって1pxずれる。** 再スケール直後の`7/0/7/7`で計算すると
幅を`640+7+7 = 654`と要求してしまい、落ち着いた枠`7/0/6/7`との差1pxが描画幅に残る。

同じ要求を再送しても直らない（要求自体が誤っているため）。**枠を測り直して再計算する
3周目**を入れると一致し、4周目は何も変えない。収束するので retry loop にはしない。

そこで整列は「素のrectで1周 → 広げたrectで2周」の3周にした。1周目は全windowを
target monitorへ乗せるためだけのもの。復元は広げないので従来どおり2周。

### 検証

- `layout_preview.py`で1〜16枚。はみ出し、重複rect、右端・下端への到達、
  再整列時の席替えを自動判定して全件パス（FAIL行ゼロ）。
- 実機3枚: `Arranged 3 of 3`を3回連続。描画rectは
  `(7,0,633,1080) (640,0,640,1080) (1280,0,640,1080)`。
  隣り合う継ぎ目の実測は**すべて0px**。右端は1920でぴったり。
- 実機7枚（テスト用に4枚開いて検証後に閉じた）: `Arranged 7 of 7`を3回連続。描画rectは
  左端の全高列`(7,0,473,1080)`と、3列×2段の`480x540`が6枚。継ぎ目はすべて0px。
  hwnd → rectの対応が3回とも完全に不変（席替えなし）。
- 実機5枚: `Arranged 5 of 5`。5列・幅480・offset 360・重なり120で均等。
- **混在DPI**: 1枚をsecondary (144 DPI)へ800x700で置くと600x525へ再スケールされる状態を
  作ってから`--arrange`。**3周化したあとの現在のcodeで**`Arranged 3 of 3`を2回連続、
  継ぎ目もすべて0px。3周化する前は`2 of 3`だった。
- `--restore`（`Restored 3 of 3`）と引数なしtoggleが引き続き期待どおり動く。

## summary 行について

`SetWindowPos` は成功を返しても、その後 window が別の geometry になることがある。
実際この不具合の最中、5回の呼び出しすべてが TRUE を返していた。
そのため summary は要求値の復唱ではなく、配置後に `GetWindowRect` で**実測**した件数を報告する。

- `Arranged N of M ...` の N = 実測が要求どおりだった件数
- `... SetWindowPos call(s) were rejected.` = 呼び出し自体が失敗した件数（別種の失敗）

この2つは別々に数えている。戻り値だけを見ていたら「5/5 成功」と誤報していた。

## 起動方法による出力の違い

| 起動 | interpreter | summary |
|---|---|---|
| タスクバー / shortcut から double-click | `pythonw.exe`（console 無し） | `sys.stdout` が `None` になり `print()` は no-op。**見えない** |
| console から `py -3 align_terminals.pyw` | console あり | **見える**（実測確認済み） |

タスクバー用途では summary が見えなくても問題ない（window が並べば目的は果たされる）。
AI から呼ぶ経路は console 経由なので summary を回収できる。

double-click 時の無出力は実測ではなく `pythonw.exe` の仕様からの推定。
診断を残したくなったら log file 出力を足すのが素直。

## DPI awareness を上げない理由

`SetProcessDpiAwarenessContext` で per-monitor aware にしても、この再スケールは
Terminal 側が境界越えに反応して行うので防げない。一方で `OFFSET` と `MIN_WIDTH` を
DPI 換算する必要が生じる。得るものが無いので、DPI-unaware のままにしてある。

summary の px 値は interpreter が見ている座標空間の値。200% の 3840x2160 上では
work area を 1920 幅と報告するが、これは正しい挙動であって bug ではない。

## Rust 移植の differential 検証 (2026-08-23)

production 経路を Rust の exe へ置き換えた。Python 版は削除せず oracle として残し、
両実装の出力を probe で突き合わせた。CLI・exit code・summary 文字列は byte 単位で
Python 版と同一（usage の program 名だけ意図的に違う）。

### 算術の differential

`tools/gen_layout_fixture.py` が Python `layout()` から 245 case（n=0..48 × 5 種類の
work area、原点が 0 でないものを含む）を記録し、`tests/layout_differential.rs` が
Rust 版との完全一致を assert する。`cargo test` で全通過。

### DPI awareness で1敗した（manifest の罠）

最初の build は manifest に `dpiAware=true`（system-DPI-aware）を埋めた。上の検証環境の
節にあった「python は system-DPI-aware」という誤記を信じたため。結果、exe は physical
座標（3840x2160）を見て、Python が書いた snapshot（1920 空間）を認識できず、
**restore すべき場面で再整列した**。summary の `width 1267px/1280px, height 2160px` が
即座に空間の違いを暴いた。

正しくは **DPI-unaware = `dpiAware=false`**。virtualized 座標こそが Python oracle の
空間で、負座標の clamp（`-7` → `-5`）も不可視枠の実測もすべてこの空間で測ってある。
build.rs は明示的に `false` を埋め、検証で exe から manifest を抽出して確認した。
default（manifest 無し）に頼らず明示するのは、この1敗を将来へ残すため。

### exe は2本（python.exe / pythonw.exe と同じ理由）

単一の windows-subsystem exe + `AttachConsole` 案は、実測で棄却した。

| 呼び出し | 出力 |
|---|---|
| bash から（pipe capture） | 取れる |
| PowerShell `$x = & exe` | **0行。しかも待機しない** |
| PowerShell `& exe \| Out-String` | 取れる（380 chars） |

素の PowerShell 呼び出しで出力が消え待機もしないのは Skill 経路として不安定なので、
計画どおり2 bin へ fallback:

- `align-terminals.exe` — console subsystem (3)。Skill と CLI 用。PowerShell の素の
  呼び出しで capture できることを実測済み。
- `align-terminalsw.exe` — windows subsystem (2)。taskbar shortcut 用。console は
  一瞬も出ない（subsystem が GUI なので原理的に出ない）。`AttachConsole` を持つので
  shell から呼べば出力は出るが、script からは呼ばない。

どちらも同じ `app::run()` を呼ぶ薄い entry point で、icon（RT_ICON/RT_GROUP_ICON）と
manifest（RT_MANIFEST, `dpiAware=false`）の埋め込みを resource 列挙で確認した。

stdout は CRLF で出す。Python が text mode で CRLF を書くため、LF のままだと
differential の diff が全行不一致になる（初回の `--help` diff で発覚）。

### 実機 differential の結果（terminal 3枚、途中から4枚）

| 項目 | 結果 |
|---|---|
| A/B: Py `--arrange` → Rs `--arrange` の drawn rect / z-order / stdout | **完全一致** |
| Rs 再整列の slot 安定性・snapshot `previous` 保持 | 不変 |
| snapshot 相互運用 | Py が書いた snapshot を Rs が restore、逆も成立 |
| 前面化: chrome 前面 → Rs `--arrange` ×5連続 | 5回とも全 terminal が chrome より前、`WS_EX_TOPMOST` 残留なし |
| 混在 DPI: secondary へ park → Rs `--arrange` | `3 of 3`、継ぎ目 0px |
| toggle 契約: 引数なし2回 / 手動 nudge 後の `--restore` | 復元→整列 / 拒否して何も動かさない |
| **最小化経路（両実装で初の実機検証）** | minimize → arrange で復元して配置、snapshot に `iconic: true`、restore で再最小化。` 1 window(s) minimized again.` まで両実装 byte 一致 |
| windowed 版 smoke | 4枚で arrange → restore 正常 |

### Rust 側で新たに守ること

- manifest の `dpiAware=false` を外さない・`true` にしない（上の1敗）。
- 2 bin 構成を保つ。script から `align-terminalsw.exe` を呼ばない。
- stdout の CRLF を保つ。summary 文字列は Python oracle と byte 一致を保つ。
- `layout()` を変えるときは .pyw と Rust の両方を変え、`tools/gen_layout_fixture.py` で
  fixture を作り直して `cargo test` を通す。
- 整数除算は全て非負 operand を保つ（Python `//` は floor、Rust `/` は truncate）。
