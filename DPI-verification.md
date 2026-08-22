# align-terminals 実機検証記録 (2026-08-22)

`align_terminals.pyw` が現在の形になった理由を残す。とくに **two-pass 配置**は、
知らずに1周へ戻すと混在 DPI 環境で必ず壊れるので、消さないこと。

## 検証環境

- Windows 11 Pro 10.0.26200
- PRIMARY monitor: 3840x2160 @ 192 DPI (200%)、work area = monitor 全体（タスクバーは auto-hide）
- secondary monitor: (-2560,0)-(0,1440) @ 144 DPI (150%)
- interpreter: `py.exe -3` (Python 3.13.5)。system-DPI-aware なので virtualized な 1920x1080 を見る
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
