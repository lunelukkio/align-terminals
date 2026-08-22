# align-terminals

Windows Terminalのwindowをprimary monitor上でcascade配置する単体tool。
5枚までは全高1段、6枚目からは右の列を上下に割って2段にする。もう一度実行すると
直前の位置へ戻る。Windows専用。標準libraryのctypesだけを使い、外部依存を持たない。

作業を始める前に`docs/handoff.md`を読むこと。設計判断の根拠は`DPI-verification.md`にある。

## 守ること

- `align_terminals.pyw`のpathとfile名を変えない。ai-dotfilesの`align-terminals` Skillが
  `~/Projects/Others/align-terminals/align_terminals.pyw`を直接指している。変更する場合は
  ai-dotfilesのcanonical source側も同時に直し、generateからinstallまで通す。
- 配置は2周適用する実装を保つ。1周に戻すと混在DPI環境で壊れる。詳細は`DPI-verification.md`。
  復元も同じ理由で2周適用する。
- summaryは`GetWindowRect`の実測を報告する。要求値の復唱に戻さない。
- 割り当ては純関数`layout()`に閉じておく。列は左から順に埋め、6枚目以降は右の列から
  順に上下へ割る。この対応が変わるとuserが覚えたwindowの位置が崩れる。
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

## 表記

- code comment、docstring、identifierは英語。
- 文書は日本語。技術用語とcode identifierは原文のまま。
