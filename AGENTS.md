# align-terminals

Windows Terminalのwindowをprimary monitor上でcascade配置する単体tool。
Windows専用。標準libraryのctypesだけを使い、外部依存を持たない。

作業を始める前に`docs/handoff.md`を読むこと。設計判断の根拠は`DPI-verification.md`にある。

## 守ること

- `align_terminals.pyw`のpathとfile名を変えない。ai-dotfilesの`align-terminals` Skillが
  `~/Projects/Others/align-terminals/align_terminals.pyw`を直接指している。変更する場合は
  ai-dotfilesのcanonical source側も同時に直し、generateからinstallまで通す。
- 配置は2周適用する実装を保つ。1周に戻すと混在DPI環境で壊れる。詳細は`DPI-verification.md`。
- summaryは`GetWindowRect`の実測を報告する。要求値の復唱に戻さない。
- 外部packageを足さない。taskbarのshortcutから直接起動されるので、virtual environmentの
  activationを前提にできない。

## 検証

見た目の確認だけでは不十分。混在DPI状態を作ってから検証する。手順は`docs/handoff.md`。

## 表記

- code comment、docstring、identifierは英語。
- 文書は日本語。技術用語とcode identifierは原文のまま。
