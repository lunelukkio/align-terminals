# 配置の安定性とtaskbar予約

## 責務の分離

- `src/layout.rs`の`layout()`は枠の形と読む順を決める。windowの割り当ては`src/placement.rs`、Win32の実測は`src/win.rs`、呼び出しは`src/app.rs`が担当する。
- Python oracleの`align_terminals.pyw`にも同じpolicyがある。新規の常駐process、設定file、依存crateは追加していない。

## taskbarの領域

- `SPI_GETWORKAREA`を基準に、primary monitor上のtaskbarの全厚をauto-hide時にも予約する。
- `SHAppBarMessage(ABM_GETTASKBARPOS)`から使うのは辺。厚みは`GetWindowRect`で配置処理と同じDPI座標系で測り、shellの矩形の倍率を仮定しない。
- monitorの端から必要境界を求め、既存のwork areaをclampする。通常表示で除外済みの領域を二重控除せず、取得失敗・不正な測定では元のwork areaへ戻る。

## 席の維持

- snapshot schema 1の`arranged`は配置順に保存されている。同じwindow集合なら、その順を再利用して席を維持する。復元後も次の整列で同じ席へ戻る。
- 外枠の上辺がwindow間で1px違うと、外枠の`(top, left)`による再sortだけでは席替えする。配置の識別と外枠の見かけ上の順序は別物。
- 枚数が変わる場合は、残ったwindowを前回中心からの移動距離の二乗和が最小になる枠へ先に割り当てる。新規windowは残った枠を使う。
- 距離は2倍した中心座標の整数演算、割り当てはrectangular Hungarian。初回の同点順は`(top, left, width, height, hwnd)`で決まり、列挙順に依存しない。
- 同じ席をそのまま使う判定には、前回と今回の枚数一致も必要。削除時に前回順を詰めるだけでは、近い位置へ移す条件を満たさない。
- 識別はwindow handleに基づく。閉じて開き直したアプリをtitleや作業内容で識別する仕組みはない。
- 前面化も枠の読む順で行う。配置3周、復元2周、`dpiAware=false`、2 bin、CRLF、明示`--restore`の拒否条件は従来どおり。

根拠: `src/placement.rs`、`src/app.rs`、`src/win.rs`、`align_terminals.pyw`、`tests/test_oracle.py`、`docs/placement-plan.md`。
