# align-terminals

Windows Terminalのwindowをprimary monitor上へ隙間なく敷き詰める単体tool。
1段は最大5枚。2枚なら1/2幅、3枚なら1/3幅、4枚以降は1/4幅なので4枚はぴったり、
5枚は均等に重なる。6枚目から2段、11枚目から3段。段数で割り切れない余りは左端の
全高列になる。1枚のときは大きさも位置も変えず前面へ出すだけ。もう一度実行すると
直前の位置へ戻る。Windows専用。標準libraryのctypesだけを使い、外部依存を持たない。

作業を始める前に`docs/handoff.md`を読むこと。設計判断の根拠は`DPI-verification.md`にある。

## 守ること

- `align_terminals.pyw`のpathとfile名を変えない。ai-dotfilesの`align-terminals` Skillが
  `~/Projects/Others/align-terminals/align_terminals.pyw`を直接指している。変更する場合は
  ai-dotfilesのcanonical source側も同時に直し、generateからinstallまで通す。
- 最終geometryは必ず2回要求する実装を保つ。1回に戻すと混在DPI環境で壊れる。
  復元も同じ理由で2回要求する。整列は隙間埋めのぶんが増えて「素のrectで1回 →
  広げたrectで2回」の3周になる。詳細は`DPI-verification.md`。
- 前面化はgeometryと分離した`raise_to_front`で行い、`HWND_TOPMOST`→`HWND_NOTOPMOST`の
  一往復を保つ。`HWND_TOP`へ戻すと、foreground windowを所有しないprocessから起動したとき
  windowがbrowserの下へclampされる（`SetWindowPos`は成功を返すので気づけない）。
  `SWP_NOMOVE | SWP_NOSIZE`も外さない。geometryを混ぜると`WM_DPICHANGED`が絡む。
- `place()`はgeometry専用に保つ。全周とも`SWP_NOZORDER`。ここでz-orderを触ると、
  復元がz-orderを触らないという不変条件が分岐頼みに戻る。
- summaryは実測を報告する。要求値の復唱に戻さない。整列時に測るのは`content_rect()`が
  返す描画rect。`layout()`が指定しているのは見える矩形であって、その外側の不可視枠の
  幅はlayoutが決めたものではない。
- 隙間埋めを外さない。`GetWindowRect`は描画されないリサイズ枠を含むので、その座標で
  隣接させると見た目には枠2つ分の隙間が空く。`outset()`がwindowごとに枠を実測し、
  要求rectをその分だけ広げる。倍率換算を持ち込まずに済むよう、枠はscriptと同じ
  座標系で測れる`GetClientRect` + `ClientToScreen`から求める。
- **整列の1周目は素のrectで置く（広げない）。** 別monitor上のwindowは枠をその
  monitorの尺度で報告し、さらにDPI再スケール直後は一瞬だけ枠が1pxずれる。
  広げるのは全windowがtarget monitorへ乗ったあとの2周と3周だけにする。
  1周目から広げると混在DPIで`N-1 of N`になる。
- **`outset()`が別monitorへはみ出す辺を広げない判定を外さない。** processはDPI-unawareな
  ので、primary monitorの外の座標は隣のmonitorの倍率で解釈される。150% monitorが左に
  ある環境で`left = -7`を要求すると`-5`に着地する。desktopの外（monitorが無い側）へ
  はみ出すのは安全なので、そちらは広げてよい。これが端をぴったりにしている。
- 割り当ては純関数`layout()`に閉じておく。順序は読む順（全高列 → 上段を左から右 →
  次の段）。`ordered`のsort keyを`(top, left)`から`(left, top)`へ戻さない。戻すと分割列の
  上下が交互に並んで、再整列のたびにwindowが席替えする。この対応が変わるとuserが
  覚えたwindowの位置が崩れる。
- 引数なしで整列と復元をtoggleする挙動を保つ。復元するのは、直前に自分が並べた実測と
  現在の実測が完全一致するときだけ。手で動かしたあとに勝手に復元してはいけない。
- 引数の契約を保つ。`--arrange`は常に整列、`--restore`は復元だけ。**`--restore`を整列へ
  fallbackさせない。** 「戻して」と頼まれて並べ替えるのが一番困る失敗なので、一致しない
  ときは何も動かさず報告する。toggleは推測してよいが、明示された指定は推測しない。
- 整列済みの状態へ`--arrange`を重ねても、snapshotの`previous`を上書きしない。上書きすると
  復元先が「整列済みの位置」になり、元の位置へ戻れなくなる。
- 外部packageを足さない。taskbarのshortcutから直接起動されるので、virtual environmentの
  activationを前提にできない。

## 検証

見た目の確認だけでは不十分。混在DPI状態を作ってから検証する。手順は`docs/handoff.md`。

配置の算術だけなら`py -3 tools/layout_preview.py`で実機なしに確認できる。ただしこれは
割り当てを見るだけで、DPIの挙動は実機でしか出ない。実機ではsummaryの`N of M`が揃うことを
見る。**window毎に目標rectが違うので、「全windowが同じ幅と高さ」は判定条件にならない。**

z-orderはsummaryに出ない。`py -3 tools/zorder_probe.py [label]`（read-only）で前面から順に
実測する。前面化を触ったときは、**browserを前面にしてから`--arrange`を複数回**繰り返して
測ること。1回だけでは通ってしまい、2回目以降に出る不具合を見逃す。

隙間も`N of M`には出ない（描画rectが目標と一致していれば揃う）。隙間を触ったときは
隣り合う描画rectの端どうしを引き算して0であることを確かめる。

## 表記

- code comment、docstring、identifierは英語。
- 文書は日本語。技術用語とcode identifierは原文のまま。
